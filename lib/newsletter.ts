import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import archive from "../data/events.json";
import { SITE_URL } from "./data";
import { NEWSLETTER_CONSENT_VERSION, newsletterConfigured } from "./newsletter-config";
import { confirmationEmail, digestEmail, normalizeEmail, selectDigestEvents, weeklyWindow } from "./newsletter-core";

const DAY = 86400;
const PREFIX = "hackathon-mi:newsletter:";
const GENERIC_SIGNUP = "Se l’indirizzo può essere iscritto, riceverai un’email di conferma. Controlla anche la cartella spam.";
const UNAVAILABLE = "Il servizio email non è disponibile in questo momento. Riprova più tardi.";

class RequestError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

type Config = { apiKey: string; segment: string; from: string; contact: string; owner: string; redisUrl: string; redisToken: string; secret: string; siteUrl: string };
type Pending = { email: string; requestedAt: string; version: string };
type WeeklyJob = { week: string; status: "creating" | "draft" | "sending" | "sent" | "empty"; eventIds: string[]; broadcastId?: string };

function config(): Config {
  if (!newsletterConfigured()) throw new RequestError(503, UNAVAILABLE);
  const env = process.env;
  const result: Config = {
    apiKey: env.RESEND_API_KEY!, segment: env.RESEND_SEGMENT_ID!, from: env.NEWSLETTER_FROM!,
    contact: env.NEWSLETTER_CONTACT_EMAIL!, owner: env.NEWSLETTER_OWNER!, redisUrl: env.UPSTASH_REDIS_REST_URL!.replace(/\/+$/, ""),
    redisToken: env.UPSTASH_REDIS_REST_TOKEN!, secret: env.CRON_SECRET!, siteUrl: SITE_URL,
  };
  return result;
}

function json(body: Record<string, unknown>, status = 200): Response {
  return Response.json(body, { status, headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow" } });
}

function failure(error: unknown): Response {
  return error instanceof RequestError ? json({ message: error.message }, error.status) : json({ message: UNAVAILABLE }, 503);
}

function checkOrigin(request: Request, cfg: Config): void {
  const origin = request.headers.get("origin");
  const canonical = new URL(cfg.siteUrl).origin;
  const local = process.env.NODE_ENV !== "production" && origin === new URL(request.url).origin && ["localhost", "127.0.0.1", "[::1]"].includes(new URL(request.url).hostname);
  if (origin !== canonical && !local) throw new RequestError(403, "Richiesta non consentita.");
  if (request.headers.get("sec-fetch-site") === "cross-site") throw new RequestError(403, "Richiesta non consentita.");
}

async function readBody(request: Request): Promise<Record<string, unknown>> {
  if (request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json") throw new RequestError(415, "Formato della richiesta non valido.");
  if (Number(request.headers.get("content-length")) > 4096) throw new RequestError(413, "Richiesta troppo grande.");
  const reader = request.body?.getReader();
  if (!reader) throw new RequestError(400, "Richiesta non valida.");
  let size = 0;
  const chunks: Uint8Array[] = [];
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 4096) { await reader.cancel(); throw new RequestError(413, "Richiesta troppo grande."); }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    const parsed: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Invalid body");
    return parsed as Record<string, unknown>;
  } catch (error) {
    if (error instanceof RequestError) throw error;
    throw new RequestError(400, "Richiesta non valida.");
  } finally { reader.releaseLock(); }
}

function keyHash(value: string, cfg: Config): string {
  return createHmac("sha256", cfg.secret).update(value).digest("hex");
}

function tokenHash(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

async function redis(cfg: Config, ...command: (string | number)[]): Promise<unknown> {
  const response = await fetch(cfg.redisUrl, {
    method: "POST", headers: { Authorization: `Bearer ${cfg.redisToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(command), cache: "no-store", signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error("Private store unavailable");
  const body = await response.json() as { result?: unknown; error?: unknown };
  if (body.error || !("result" in body)) throw new Error("Private store unavailable");
  return body.result;
}

async function resend(cfg: Config, path: string, method = "GET", payload?: unknown, idempotency?: string): Promise<{ status: number; data: Record<string, unknown> }> {
  const response = await fetch(`https://api.resend.com${path}`, {
    method, headers: { Authorization: `Bearer ${cfg.apiKey}`, "Content-Type": "application/json", ...(idempotency ? { "Idempotency-Key": idempotency } : {}) },
    ...(payload ? { body: JSON.stringify(payload) } : {}), cache: "no-store", signal: AbortSignal.timeout(8000),
  });
  // Provider messages may include addresses or tokens. They are never logged or returned.
  const data = await response.json().catch(() => ({})) as Record<string, unknown>;
  return { status: response.status, data };
}

function requireSuccess(response: { status: number }): void {
  if (response.status < 200 || response.status >= 300) throw new Error("Email provider unavailable");
}

async function limit(cfg: Config, suffix: string, maximum: number, ttl: number): Promise<void> {
  const count = Number(await redis(cfg, "EVAL", "local n = redis.call('INCR', KEYS[1]); if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]); end; return n;", 1, `${PREFIX}limit:${suffix}`, ttl));
  if (count > maximum) throw new RequestError(429, "Troppe richieste. Riprova tra un’ora.");
}

async function ipLimit(request: Request, cfg: Config, action: string, maximum: number): Promise<void> {
  // Vercel overwrites x-forwarded-for. Other deployments share a conservative bucket.
  const ip = process.env.VERCEL ? request.headers.get("x-forwarded-for")?.split(",")[0].trim() || "unknown" : "local";
  const hash = keyHash(`ip:${ip}`, cfg);
  await limit(cfg, `${action}:${hash}`, maximum, 3600);
  await limit(cfg, `daily:${action}:${hash}`, maximum * 4, DAY);
}

async function release(cfg: Config, key: string, lock: string): Promise<void> {
  await redis(cfg, "EVAL", "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]); end; return 0;", 1, key, lock);
}

export async function subscribe(request: Request): Promise<Response> {
  try {
    const cfg = config();
    checkOrigin(request, cfg);
    const body = await readBody(request);
    if (typeof body.website === "string" && body.website.trim()) return json({ message: GENERIC_SIGNUP }, 202);
    const email = normalizeEmail(body.email);
    if (!email || body.consent !== true) throw new RequestError(400, "Inserisci un indirizzo email valido e accetta l’informativa privacy.");
    await ipLimit(request, cfg, "subscribe", 5);
    const emailHash = keyHash(`email:${email}`, cfg);
    const fresh = await redis(cfg, "SET", `${PREFIX}cooldown:${emailHash}`, "1", "NX", "EX", 3600);
    if (fresh !== "OK") return json({ message: GENERIC_SIGNUP }, 202);
    await limit(cfg, "send-daily", 100, DAY);
    const token = randomBytes(32).toString("hex");
    const pending: Pending = { email, requestedAt: new Date().toISOString(), version: NEWSLETTER_CONSENT_VERSION };
    await redis(cfg, "SET", `${PREFIX}pending:${tokenHash(token)}`, JSON.stringify(pending), "EX", DAY);
    const link = `${cfg.siteUrl}/newsletter/confirm#token=${token}`;
    requireSuccess(await resend(cfg, "/emails", "POST", {
      from: cfg.from, to: [email], reply_to: cfg.contact,
      ...confirmationEmail(link, cfg.owner, cfg.contact),
    }, `newsletter-confirm-${tokenHash(token)}`));
    return json({ message: GENERIC_SIGNUP }, 202);
  } catch (error) { return failure(error); }
}

export async function confirm(request: Request): Promise<Response> {
  let cfg: Config | undefined;
  let lockKey = "";
  let lock = "";
  try {
    cfg = config();
    checkOrigin(request, cfg);
    const body = await readBody(request);
    if (typeof body.token !== "string" || !/^[a-f0-9]{64}$/.test(body.token)) throw new RequestError(400, "Link di conferma non valido.");
    await ipLimit(request, cfg, "confirm", 20);
    const hash = tokenHash(body.token);
    const doneKey = `${PREFIX}confirmed:${hash}`;
    const success = () => json({ message: "Iscrizione confermata. Riceverai una email quando ci saranno nuovi hackathon nella settimana." });
    if (await redis(cfg, "GET", doneKey)) return success();
    const pendingKey = `${PREFIX}pending:${hash}`;
    const stored = await redis(cfg, "GET", pendingKey);
    if (typeof stored !== "string") throw new RequestError(410, "Il link è scaduto o non è valido. Richiedi una nuova iscrizione dal sito.");
    const pending = JSON.parse(stored) as Pending;
    const email = normalizeEmail(pending.email);
    if (!email || !pending.version || !Number.isFinite(Date.parse(pending.requestedAt))) throw new Error("Invalid pending subscription");
    const emailHash = keyHash(`email:${email}`, cfg);
    lockKey = `${PREFIX}contact-lock:${emailHash}`;
    lock = randomBytes(16).toString("hex");
    if (await redis(cfg, "SET", lockKey, lock, "NX", "EX", 120) !== "OK") { lock = ""; throw new RequestError(409, "La conferma è già in corso. Riprova tra qualche secondo."); }
    const path = `/contacts/${encodeURIComponent(email)}`;
    const existing = await resend(cfg, path);
    if (existing.status === 404) {
      requireSuccess(await resend(cfg, "/contacts", "POST", { email, segments: [{ id: cfg.segment }] }));
    } else {
      requireSuccess(existing);
      if (existing.data.unsubscribed !== false) throw new RequestError(409, "Questo indirizzo risulta disiscritto. Contattaci per gestire una nuova iscrizione.");
      requireSuccess(await resend(cfg, `${path}/segments/${encodeURIComponent(cfg.segment)}`, "POST"));
    }
    // Commit consumption and minimal consent evidence together after the provider succeeds.
    const evidence = JSON.stringify({ requestedAt: pending.requestedAt, confirmedAt: new Date().toISOString(), version: pending.version });
    await redis(cfg, "EVAL", "redis.call('SET', KEYS[1], '1', 'EX', ARGV[1]); redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3]); redis.call('DEL', KEYS[3]); return 1;", 3, doneKey, `${PREFIX}consent:${emailHash}`, pendingKey, DAY, evidence, 365 * DAY);
    return success();
  } catch (error) { return failure(error); }
  finally { if (cfg && lock) await release(cfg, lockKey, lock).catch(() => {}); }
}

async function saveJob(cfg: Config, job: WeeklyJob): Promise<void> {
  await redis(cfg, "SET", `${PREFIX}week:${job.week}`, JSON.stringify(job));
}

async function finishJob(cfg: Config, job: WeeklyJob): Promise<void> {
  const finished: WeeklyJob = { ...job, status: "sent" };
  const keys = [`${PREFIX}week:${job.week}`, `${PREFIX}weekly-active`, ...job.eventIds.map(id => `${PREFIX}sent-event:${tokenHash(id)}`)];
  await redis(cfg, "EVAL", "redis.call('SET', KEYS[1], ARGV[1]); redis.call('DEL', KEYS[2]); for i = 3, #KEYS do redis.call('SET', KEYS[i], '1'); end; return 1;", keys.length, ...keys, JSON.stringify(finished));
}

async function reconcile(cfg: Config, job: WeeklyJob): Promise<boolean> {
  if (!job.broadcastId) return false;
  const broadcast = await resend(cfg, `/broadcasts/${encodeURIComponent(job.broadcastId)}`);
  requireSuccess(broadcast);
  if (["sent", "sending", "queued", "scheduled"].includes(String(broadcast.data.status))) {
    await finishJob(cfg, job);
    return true;
  }
  return false;
}

export async function weekly(request: Request): Promise<Response> {
  let cfg: Config | undefined;
  let lock = "";
  const lockKey = `${PREFIX}weekly-lock`;
  try {
    const secret = process.env.CRON_SECRET || "";
    const header = request.headers.get("authorization") || "";
    const expected = Buffer.from(`Bearer ${secret}`);
    const received = Buffer.from(header);
    if (secret.length < 32 || expected.length !== received.length || !timingSafeEqual(expected, received)) return json({ message: "Non autorizzato." }, 401);
    cfg = config();
    lock = randomBytes(16).toString("hex");
    if (await redis(cfg, "SET", lockKey, lock, "NX", "EX", 120) !== "OK") { lock = ""; return json({ status: "in_progress" }, 202); }
    const now = new Date();
    const { id: week } = weeklyWindow(now);
    const activeWeek = await redis(cfg, "GET", `${PREFIX}weekly-active`);
    if (typeof activeWeek === "string" && activeWeek !== week) {
      const previous = await redis(cfg, "GET", `${PREFIX}week:${activeWeek}`);
      if (typeof previous !== "string" || !await reconcile(cfg, JSON.parse(previous) as WeeklyJob)) return json({ status: "needs_review", message: "Verificare il broadcast precedente prima di un nuovo invio." }, 503);
    }
    const saved = await redis(cfg, "GET", `${PREFIX}week:${week}`);
    let job: WeeklyJob | undefined = typeof saved === "string" ? JSON.parse(saved) as WeeklyJob : undefined;
    if (job?.status === "sent" || job?.status === "empty") return json({ status: job.status });
    if (job && await reconcile(cfg, job)) return json({ status: "sent" });
    if (job?.status === "creating" || job?.status === "sending") return json({ status: "needs_review", message: "Esito del provider incerto: verificare il broadcast salvato prima di riprovare." }, 503);
    if (!job) {
      const candidates = selectDigestEvents(archive, now);
      const seen = candidates.length ? await redis(cfg, "MGET", ...candidates.map(event => `${PREFIX}sent-event:${tokenHash(event.id)}`)) as unknown[] : [];
      const events = candidates.filter((_, index) => !seen[index]);
      if (!events.length) { await saveJob(cfg, { week, status: "empty", eventIds: [] }); return json({ status: "empty", count: 0 }); }
      job = { week, status: "creating", eventIds: events.map(event => event.id) };
      // Record the attempt before calling the provider. An ambiguous create can only leave an unsent draft.
      await redis(cfg, "EVAL", "redis.call('SET', KEYS[1], ARGV[1]); redis.call('SET', KEYS[2], ARGV[2]); return 1;", 2, `${PREFIX}week:${week}`, `${PREFIX}weekly-active`, JSON.stringify(job), week);
      const created = await resend(cfg, "/broadcasts", "POST", {
        segment_id: cfg.segment, from: cfg.from, reply_to: cfg.contact,
        name: `Hackathon Milano · ${week}`, send: false,
        ...digestEmail(events, cfg.siteUrl, cfg.owner, cfg.contact),
      });
      requireSuccess(created);
      if (typeof created.data.id !== "string" || !created.data.id) throw new Error("Missing broadcast reference");
      job = { ...job, status: "draft", broadcastId: created.data.id };
      await saveJob(cfg, job);
    }
    if (!job.broadcastId || job.status !== "draft") throw new Error("Invalid weekly state");
    const broadcast = await resend(cfg, `/broadcasts/${encodeURIComponent(job.broadcastId)}`);
    requireSuccess(broadcast);
    if (broadcast.data.status !== "draft") return json({ status: "needs_review" }, 503);
    const broadcastId = job.broadcastId;
    job = { ...job, status: "sending" };
    await saveJob(cfg, job);
    requireSuccess(await resend(cfg, `/broadcasts/${encodeURIComponent(broadcastId)}/send`, "POST", {}));
    await finishJob(cfg, job);
    return json({ status: "sent", count: job.eventIds.length });
  } catch (error) { return failure(error); }
  finally { if (cfg && lock) await release(cfg, lockKey, lock).catch(() => {}); }
}
