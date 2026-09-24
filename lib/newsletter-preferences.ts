export const NEWSLETTER_SEEN_KEY = "hackathon-mi:newsletter-invite-seen";
export const NEWSLETTER_CONFIRMED_KEY = "hackathon-mi:newsletter-confirmed";
export const NEWSLETTER_STORAGE_EVENT = "hackathon-mi:newsletter-preferences-changed";

export type NewsletterPreferences = { seen: boolean; confirmed: boolean };
type ReadableStorage = Pick<Storage, "getItem">;
type WritableStorage = Pick<Storage, "setItem">;

// Keep this visit consistent when the browser blocks persistent storage.
const currentVisit: NewsletterPreferences = { seen: false, confirmed: false };

function browserStorage(): Storage | undefined {
  try { return typeof window === "undefined" ? undefined : window.localStorage; }
  catch { return undefined; }
}

export function readNewsletterPreferences(storage: ReadableStorage | undefined = browserStorage()): NewsletterPreferences {
  const read = (key: string): boolean => {
    try { return storage?.getItem(key) === "1"; }
    catch { return false; }
  };
  return {
    seen: currentVisit.seen || read(NEWSLETTER_SEEN_KEY),
    confirmed: currentVisit.confirmed || read(NEWSLETTER_CONFIRMED_KEY),
  };
}

function notifyChange(): void {
  try {
    if (typeof window !== "undefined") window.dispatchEvent(new Event(NEWSLETTER_STORAGE_EVENT));
  } catch { /* A browser preference must not block the subscription flow. */ }
}

function write(storage: WritableStorage | undefined, key: string): void {
  try { storage?.setItem(key, "1"); }
  catch { /* The flag remains effective for this visit. */ }
}

export function markNewsletterInviteSeen(storage: WritableStorage | undefined = browserStorage()): void {
  currentVisit.seen = true;
  write(storage, NEWSLETTER_SEEN_KEY);
  notifyChange();
}

export function markNewsletterConfirmed(storage: WritableStorage | undefined = browserStorage()): void {
  currentVisit.seen = true;
  currentVisit.confirmed = true;
  write(storage, NEWSLETTER_SEEN_KEY);
  write(storage, NEWSLETTER_CONFIRMED_KEY);
  notifyChange();
}

export function shouldAutoPrompt(available: boolean, mode: string | undefined, preferences: NewsletterPreferences): boolean {
  if (!available || preferences.confirmed || mode === "off") return false;
  if (mode === "always") return true;
  return !preferences.seen;
}
