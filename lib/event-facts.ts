/** Reviewed facts are separate from the automatically collected archive. */
export interface EventFact { label: string; value: string; sourceUrl: string }
export interface EventRecord {
  id: string;
  slug: string;
  title: string;
  url: string;
  sourceLabel: string;
  checkedAt: string;
  startDate: string;
  endDate: string;
  location: string;
  organizer: string;
  facts: EventFact[];
  missing: string[];
  venue?: { name: string; streetAddress: string; addressLocality: string; addressCountry: string };
}

export function safeSourceUrl(value: unknown): string {
  if (typeof value !== "string") return "";
  try {
    const url = new URL(value.trim());
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : "";
  } catch { return ""; }
}

export function calendarDate(value: unknown): string {
  if (typeof value !== "string") return "";
  let input = value.trim();
  const months = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
  const italian = input.toLowerCase().match(/^(\d{1,2})\s*([a-z]+)\s*(\d{4})$/);
  if (italian && months.includes(italian[2])) input = `${italian[3]}-${String(months.indexOf(italian[2]) + 1).padStart(2, "0")}-${italian[1].padStart(2, "0")}`;
  const match = input.match(/^(\d{4}-\d{2}-\d{2})(?:$|T\d{2}:\d{2})/);
  if (!match) return "";
  const date = new Date(`${match[1]}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === match[1] ? match[1] : "";
}

const text = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;

/** Fail the build on ambiguous curated data, rather than publish an incorrect page. */
export function validateEventRecords(value: unknown): EventRecord[] {
  if (!Array.isArray(value)) throw new Error("Event details must be an array");
  const ids = new Set<string>();
  const slugs = new Set<string>();
  return value.map((item) => {
    const e = item as EventRecord;
    if (!e || ![e.id, e.title, e.sourceLabel, e.location, e.organizer].every(text) || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(e.slug || "") || e.slug.length > 120) throw new Error("Incomplete event identity");
    if (ids.has(e.id) || slugs.has(e.slug)) throw new Error(`Duplicate event detail: ${e.slug}`);
    if (!safeSourceUrl(e.url) || !calendarDate(e.checkedAt) || e.checkedAt !== calendarDate(e.checkedAt)) throw new Error(`Invalid source review: ${e.slug}`);
    if (!calendarDate(e.startDate) || e.startDate !== calendarDate(e.startDate) || !calendarDate(e.endDate) || e.endDate !== calendarDate(e.endDate) || e.endDate < e.startDate) throw new Error(`Invalid event dates: ${e.slug}`);
    if (!Array.isArray(e.facts) || e.facts.length < 3 || e.facts.some((f) => !f || !text(f.label) || !text(f.value) || !safeSourceUrl(f.sourceUrl))) throw new Error(`Insufficient sourced facts: ${e.slug}`);
    if (!Array.isArray(e.missing) || e.missing.some((v) => !text(v))) throw new Error(`Invalid missing fields: ${e.slug}`);
    if (e.venue && ![e.venue.name, e.venue.streetAddress, e.venue.addressLocality, e.venue.addressCountry].every(text)) throw new Error(`Invalid venue: ${e.slug}`);
    ids.add(e.id); slugs.add(e.slug);
    return e;
  });
}

/** Remove markup and obvious technical snippets; never fill missing content. */
export function cleanEventDescription(value: unknown): string {
  if (typeof value !== "string") return "";
  const clean = value.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "").replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, "").replace(/<[^>]+>/g, " ").replace(/&nbsp;|&#160;/g, " ").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
  if (/^(?:\{|\[|speaker-area|Skip to|Salta al|Accept (?:all )?cookies|Accetta (?:tutti )?i cookie)/i.test(clean)) return "";
  return clean;
}
