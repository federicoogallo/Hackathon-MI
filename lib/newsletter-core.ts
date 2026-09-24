export interface DigestEvent {
  id: string;
  title: string;
  url: string;
  date: string;
  location: string;
}

export function normalizeEmail(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const email = value.trim().toLowerCase();
  if (email.length > 254 || !/^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$/.test(email)) return null;
  const local = email.split("@")[0];
  return local.length <= 64 && !local.startsWith(".") && !local.endsWith(".") && !local.includes("..") ? email : null;
}

/** The latest completed interval, anchored to Monday at 08:00 UTC. */
export function weeklyWindow(now = new Date()) {
  const end = new Date(now);
  end.setUTCHours(8, 0, 0, 0);
  end.setUTCDate(end.getUTCDate() - (end.getUTCDay() + 6) % 7);
  if (end > now) end.setUTCDate(end.getUTCDate() - 7);
  const start = new Date(end.getTime() - 7 * 86400_000);
  return { start, end, id: end.toISOString().slice(0, 10) };
}

function timestamp(value: unknown): number {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) return NaN;
  // Older GitHub Actions archives used offset-free timestamps on UTC runners.
  return Date.parse(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
}

export function selectDigestEvents(raw: unknown, now = new Date()): DigestEvent[] {
  const archive = raw as { events?: unknown } | null;
  const list = Array.isArray(archive?.events) ? archive.events : Object.values(archive?.events || {});
  const { start, end } = weeklyWindow(now);
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome" }).format(now);
  const selected = new Map<string, DigestEvent>();
  for (const item of list) {
    if (!item || typeof item !== "object") continue;
    const event = item as Record<string, unknown>;
    if (event.is_hackathon !== true || !["ai_verified", "manual_approved"].includes(String(event.review_status))) continue;
    const discovered = timestamp(event.discovered_at);
    const reviewed = timestamp(event.reviewed_at);
    const published = Math.max(Number.isFinite(discovered) ? discovered : 0, Number.isFinite(reviewed) ? reviewed : 0);
    if (published < start.getTime() || published >= end.getTime()) continue;
    const id = typeof event.id === "string" ? event.id.trim() : "";
    if (!id || id.length > 200 || typeof event.url !== "string") continue;
    let url: URL;
    try { url = new URL(event.url); } catch { continue; }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) continue;
    const rawDate = typeof event.date_str === "string" ? event.date_str.trim() : "";
    const european = rawDate.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
    const iso = rawDate.match(/^\d{4}-\d{2}-\d{2}/)?.[0] || (european ? `${european[3]}-${european[2].padStart(2, "0")}-${european[1].padStart(2, "0")}` : "");
    if (!iso && rawDate && !/^(tbd|tba|da (definire|confermare)|data da (definire|confermare))$/i.test(rawDate)) continue;
    if (iso) {
      const date = new Date(`${iso}T00:00:00Z`);
      if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== iso || iso < today) continue;
    }
    selected.set(id, {
      id,
      title: String(event.title || "Hackathon a Milano").trim().slice(0, 240),
      url: url.href,
      date: iso,
      location: String(event.location || "Milano e dintorni").trim().slice(0, 120),
    });
  }
  return [...selected.values()].sort((a, b) => (a.date || "9999").localeCompare(b.date || "9999") || a.title.localeCompare(b.title));
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]!);
}

function dateLabel(value: string): string {
  return value ? new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T12:00:00Z`)) : "Data da confermare";
}

function emailFrame(content: string, owner: string, contact: string): string {
  return `<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f5f4ee;color:#20231f;font-family:Arial,Helvetica,sans-serif"><main style="max-width:600px;margin:0 auto;padding:40px 24px"><p style="font-size:13px;letter-spacing:2px;color:#a53b1d">HACKATHON MILANO</p>${content}<footer style="margin-top:32px;border-top:1px solid #d7d9ce;padding-top:20px;font-size:12px;line-height:1.7;color:#596156">${escapeHtml(owner)} · <a style="color:#596156" href="mailto:${escapeHtml(contact)}">${escapeHtml(contact)}</a></footer></main></body></html>`;
}

export function confirmationEmail(link: string, owner: string, contact: string) {
  return {
    subject: "Conferma la tua iscrizione · Hackathon Milano",
    html: emailFrame(`<h1 style="font-size:32px;line-height:1.15">La prossima sfida ti aspetta.</h1><p style="line-height:1.7">Conferma il tuo indirizzo per ricevere, ogni settimana, i nuovi hackathon a Milano e dintorni.</p><p style="margin:28px 0"><a href="${escapeHtml(link)}" style="display:inline-block;padding:16px 22px;background:#17241e;color:#fff;text-decoration:none;border-radius:8px">Conferma iscrizione →</a></p><p style="font-size:13px;line-height:1.7">Il link scade tra 24 ore. Se non hai richiesto questa email, ignorala: non sarai iscritto.</p>`, owner, contact),
    text: `Conferma la tua iscrizione a Hackathon Milano\n\nRicevi una email settimanale con i nuovi hackathon a Milano e dintorni.\n\n${link}\n\nIl link scade tra 24 ore. Se non hai richiesto questa email, ignorala: non sarai iscritto.\n\n${owner}\n${contact}`,
  };
}

export function digestEmail(events: DigestEvent[], siteUrl: string, owner: string, contact: string) {
  const unsubscribe = "{{ unsubscribe }}";
  const heading = events.length === 1 ? "Una nuova sfida da scoprire." : `${events.length} nuove sfide da scoprire.`;
  const cards = events.map(event => `<article style="border-top:1px solid #d7d9ce;padding:24px 0"><p style="font-size:13px;color:#596156">${escapeHtml(dateLabel(event.date))} · ${escapeHtml(event.location)}</p><h2 style="font-size:22px;line-height:1.3;margin:12px 0"><a style="color:#17241e;text-decoration:none" href="${escapeHtml(event.url)}">${escapeHtml(event.title)} ↗</a></h2></article>`).join("");
  return {
    subject: `Hackathon Milano · ${events.length === 1 ? "1 nuovo hackathon" : `${events.length} nuovi hackathon`}`,
    html: emailFrame(`<h1 style="font-size:34px;line-height:1.15">${heading}</h1><p style="line-height:1.7">Le novità entrate nel calendario questa settimana. Controlla sempre requisiti e scadenze sul sito dell’organizzatore.</p>${cards}<p><a href="${escapeHtml(siteUrl)}/#events" style="color:#a53b1d">Esplora tutti gli hackathon →</a></p><p style="font-size:12px;line-height:1.7">Ricevi questa email perché hai confermato l’iscrizione. <a href="${unsubscribe}" style="color:#596156">Disiscriviti</a> · <a href="${escapeHtml(siteUrl)}/privacy" style="color:#596156">Privacy</a></p>`, owner, contact),
    text: `${heading}\n\nLe novità entrate nel calendario questa settimana. Controlla requisiti e scadenze sul sito dell’organizzatore.\n\n${events.map(event => `${event.title}\n${dateLabel(event.date)} · ${event.location}\n${event.url}`).join("\n\n")}\n\nTutti gli hackathon: ${siteUrl}/#events\nPrivacy: ${siteUrl}/privacy\nDisiscriviti: ${unsubscribe}\n\n${owner}\n${contact}`,
  };
}
