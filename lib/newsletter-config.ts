import { SITE_URL } from "./data";
import { normalizeEmail } from "./newsletter-core";

export function newsletterConfigured(): boolean {
  const present = process.env.NEWSLETTER_ENABLED === "true" && [
    "BREVO_API_KEY", "BREVO_LIST_ID", "NEWSLETTER_FROM", "NEWSLETTER_CONTACT_EMAIL",
    "NEWSLETTER_OWNER", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "CRON_SECRET",
  ].every(key => !!process.env[key]?.trim());
  const sender = normalizeEmail(process.env.NEWSLETTER_FROM);
  const listId = Number(process.env.BREVO_LIST_ID);
  if (!present || process.env.CRON_SECRET!.length < 32 || !normalizeEmail(process.env.NEWSLETTER_CONTACT_EMAIL)
    || !sender || sender.endsWith("@vercel.app") || sender.split("@")[1].endsWith(".vercel.app")
    || !Number.isSafeInteger(listId) || listId < 1) return false;
  try {
    const redis = new URL(process.env.UPSTASH_REDIS_REST_URL!);
    const site = new URL(SITE_URL);
    const local = process.env.NODE_ENV !== "production" && site.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(site.hostname);
    return redis.protocol === "https:" && !redis.username && !redis.password && !site.username && !site.password && (site.protocol === "https:" || local);
  } catch { return false; }
}

export const NEWSLETTER_CONSENT_VERSION = "2026-09-24";
