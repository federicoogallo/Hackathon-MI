/**
 * Data layer: legge i JSON prodotti dalla pipeline Python (../data/) al
 * momento della build (SSG). Vercel rebuilda ad ogni push, incluso il
 * commit giornaliero della GitHub Action che aggiorna events.json.
 */
import fs from "node:fs";
import path from "node:path";

export const REPO_URL = "https://github.com/federicoogallo/Hackathon-MI";

export interface HackEvent {
  id: string;
  title: string;
  url: string;
  source: string;
  dateStr: string;
  dateIso: string;
  day: string;
  month: string;
  dateCompact: string;
  location: string;
  description: string;
  confidence: number;
  reviewStatus: string;
  issueOk: string;
  issueDoubt: string;
  searchBlob: string;
}

export interface ReviewCandidate {
  id: string;
  title: string;
  url: string;
  source: string;
  reason: string;
  confidence: number;
  location: string;
  dateCompact: string;
  issueOk: string;
  issueDoubt: string;
}

export interface SiteData {
  events: HackEvent[];
  reviewCount: number;
  lastScan: string;
  monthsCovered: number;
  statusLabel: string;
  statusOk: boolean;
}

const MONTHS_IT = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];

function dataDir(): string | null {
  for (const p of [
    path.join(process.cwd(), "..", "data"),
    path.join(process.cwd(), "data"),
    path.join(process.cwd(), "..", "..", "data"),
  ]) {
    if (fs.existsSync(path.join(p, "events.json"))) return p;
  }
  return null;
}

function readJson(file: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(file, "utf-8"));
  } catch {
    return null;
  }
}

function todayRome(): string {
  // YYYY-MM-DD nel fuso di riferimento del progetto
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome" }).format(new Date());
}

function parseIso(dateStr: string): string {
  const m = (dateStr || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[1]}-${m[2]}-${m[3]}` : "";
}

function fmtCompact(iso: string, raw: string): string {
  if (!iso) return (raw || "").trim().slice(0, 25);
  const [y, mo, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS_IT[mo - 1]} ${y}`;
}

function issueUrl(
  e: { title?: string; url?: string; source?: string; location?: string; date_str?: string; confidence?: number },
  mode: "confirmed_ok" | "confirmed_doubt" | "review_ok" | "review_doubt",
): string {
  const title = (e.title || "Senza titolo").trim();
  const kinds: Record<string, [string, string]> = {
    confirmed_ok: [`[VALUTAZIONE OK] ${title}`, "Conferma evento sicuro"],
    confirmed_doubt: [`[DUBBIO] ${title}`, "Segnalazione dubbio su evento pubblicato"],
    review_ok: [`[REVIEW OK] ${title}`, "Conferma candidato incerto"],
    review_doubt: [`[REVIEW DUBBIO] ${title}`, "Segnalazione candidato incerto"],
  };
  const [issueTitle, kind] = kinds[mode];
  const body =
    `Tipo valutazione: ${kind}\n` +
    `Titolo: ${title}\n` +
    `URL: ${e.url || ""}\n` +
    `Source: ${e.source || ""}\n` +
    `Location: ${e.location || "(non specificata)"}\n` +
    `Data: ${e.date_str || "TBD"}\n` +
    `Confidence AI: ${Math.round((e.confidence || 0) * 100)}%\n\n` +
    "Note utente:\n- \n\n" +
    "Nota: gli utenti non eliminano eventi direttamente; la decisione resta ai maintainer.\n";
  const params = new URLSearchParams({ title: issueTitle, body });
  return `${REPO_URL}/issues/new?${params.toString()}`;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export function getSiteData(): SiteData {
  const dir = dataDir();
  const raw = dir ? (readJson(path.join(dir, "events.json")) as any) : null;
  const all: any[] = raw
    ? Array.isArray(raw.events)
      ? raw.events
      : Object.values(raw.events || {})
    : [];
  const today = todayRome();

  const upcoming = all
    .filter((e) => e && e.is_hackathon)
    .filter((e) => {
      const iso = parseIso(e.date_str || "");
      return !iso || iso >= today; // senza data = ancora valido (TBD)
    })
    .sort((a, b) => {
      const ia = parseIso(a.date_str || "") || "9999-12-31";
      const ib = parseIso(b.date_str || "") || "9999-12-31";
      return ia.localeCompare(ib);
    });

  const events: HackEvent[] = upcoming.map((e, i) => {
    const iso = parseIso(e.date_str || "");
    const [_, mo, d] = iso ? iso.split("-").map(Number) : [0, 0, 0];
    let desc = String(e.description || "").trim().replace(/\n/g, " ");
    if (desc.length > 210) desc = desc.slice(0, 210).replace(/\s+\S*$/, "") + "...";
    const title = String(e.title || "Senza titolo").trim();
    const location = String(e.location || "Milano").trim() || "Milano";
    const source = String(e.source || "").trim();
    return {
      id: String(e.id || i),
      title,
      url: String(e.url || "#"),
      source,
      dateStr: String(e.date_str || ""),
      dateIso: iso,
      day: iso ? String(d) : "",
      month: iso ? MONTHS_IT[mo - 1].toUpperCase() : "",
      dateCompact: fmtCompact(iso, e.date_str || ""),
      location,
      description: desc,
      confidence: Number(e.confidence || 0),
      reviewStatus: String(e.review_status || "ai_verified"),
      issueOk: issueUrl(e, "confirmed_ok"),
      issueDoubt: issueUrl(e, "confirmed_doubt"),
      searchBlob: `${title} ${desc} ${location} ${source}`.toLowerCase(),
    };
  });

  const months = new Set(events.map((e) => e.month).filter(Boolean));

  // review queue
  const rq = dir ? (readJson(path.join(dir, "review_queue.json")) as any) : null;
  const candidates: any[] = Array.isArray(rq?.candidates) ? rq.candidates : [];

  // scan status (last_report.json e' gitignored: assente in build = OK).
  // Un report piu' vecchio dell'ultimo scan riuscito non conta (parita' con html_export).
  let statusLabel = "OK";
  const report = dir ? (readJson(path.join(dir, "last_report.json")) as any) : null;
  if (report) {
    const repDay = String(report.date || "").slice(0, 10);
    const scanDay = String(raw?.last_check || "").slice(0, 10);
    const stale = /^\d{4}-\d{2}-\d{2}$/.test(repDay) && /^\d{4}-\d{2}-\d{2}$/.test(scanDay) && repDay < scanDay;
    if (!stale) {
      const failures = Array.isArray(report.failed_collectors) ? report.failed_collectors.length : 0;
      const st = String(report.status || "completed");
      if (st === "llm_failed_preserved") statusLabel = "LLM non attivo";
      else if (st !== "completed" || failures > 0) statusLabel = "Da controllare";
    }
  }

  // last scan label
  let lastScan = "";
  const lastCheck = String(raw?.last_check || "");
  if (lastCheck) {
    const dt = new Date(lastCheck);
    if (!isNaN(dt.getTime())) {
      const fmt = new Intl.DateTimeFormat("it-IT", {
        timeZone: "Europe/Rome",
        day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      }).formatToParts(dt);
      const g = (t: string) => fmt.find((p) => p.type === t)?.value || "";
      lastScan = `${g("day")} ${g("month")} ${g("year")} alle ${g("hour")}:${g("minute")}`;
    }
  }

  return {
    events,
    reviewCount: candidates.length,
    lastScan,
    monthsCovered: months.size,
    statusLabel,
    statusOk: statusLabel === "OK",
  };
}

export function getReviewData(): { candidates: ReviewCandidate[]; lastScan: string } {
  const dir = dataDir();
  const rq = dir ? (readJson(path.join(dir, "review_queue.json")) as any) : null;
  const list: any[] = Array.isArray(rq?.candidates) ? rq.candidates : [];
  const { lastScan } = getSiteData();
  return {
    lastScan,
    candidates: list.map((c) => ({
      id: String(c.id || "").slice(0, 12),
      title: String(c.title || "Senza titolo").trim(),
      url: String(c.url || "#"),
      source: String(c.source || ""),
      reason: String(c.review_reason || "Motivazione non disponibile"),
      confidence: Math.round(Number(c.confidence || 0) * 100),
      location: String(c.location || "Milano"),
      dateCompact: fmtCompact(parseIso(c.date_str || ""), c.date_str || "") || "TBD",
      issueOk: issueUrl(c, "review_ok"),
      issueDoubt: issueUrl(c, "review_doubt"),
    })),
  };
}
