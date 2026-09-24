const PUBLIC_PAGES = new Set(["/", "/review", "/privacy"]);

/** Keep search terms, confirmation tokens and unknown paths out of analytics. */
export function analyticsPageUrl(raw: string, origin: string): string | null {
  try {
    const url = new URL(raw);
    if (url.origin !== origin || !PUBLIC_PAGES.has(url.pathname)) return null;
    return `${origin}${url.pathname}`;
  } catch { return null; }
}
