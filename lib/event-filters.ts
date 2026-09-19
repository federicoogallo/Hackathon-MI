import type { HackEvent } from "@/lib/data";

export type EventPeriod = "all" | "week" | "month" | "undated";
export type EventFilters = { q: string; period: EventPeriod; source: string; saved: boolean; order: "date" | "name"; view: "grid" | "list" };
export const DEFAULT_EVENT_FILTERS: EventFilters = { q: "", period: "all", source: "all", saved: false, order: "date", view: "grid" };

export function sourceLabel(source: string): string {
  const names: Record<string, string> = { web_search: "Ricerca web", eventbrite: "Eventbrite", meetup: "Meetup", luma: "Luma", devpost: "Devpost", linkedin: "LinkedIn", manual: "Segnalazione manuale" };
  return names[source.toLowerCase()] || source.replace(/[_-]+/g, " ").replace(/^./, (char) => char.toUpperCase()) || "Fonte esterna";
}

export function readEventFilters(search: string): EventFilters {
  const params = new URLSearchParams(search);
  const period = params.get("period");
  return { q: params.get("q") || "", period: period === "week" || period === "month" || period === "undated" ? period : "all", source: params.get("source") || "all", saved: params.get("saved") === "1", order: params.get("order") === "name" ? "name" : "date", view: params.get("view") === "list" ? "list" : "grid" };
}

export function writeEventFilters(url: URL, filters: EventFilters): string {
  const values: Record<string, string> = { q: filters.q, period: filters.period === "all" ? "" : filters.period, source: filters.source === "all" ? "" : filters.source, saved: filters.saved ? "1" : "", order: filters.order === "date" ? "" : filters.order, view: filters.view === "grid" ? "" : filters.view };
  for (const [key, value] of Object.entries(values)) { if (value) url.searchParams.set(key, value); else url.searchParams.delete(key); }
  return `${url.pathname}${url.search}${url.hash}`;
}

export function validEventDate(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : null;
}

export function todayInRome(now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function matchesPeriod(dateIso: string, period: EventPeriod, today: string): boolean {
  if (period === "all") return true;
  const date = validEventDate(dateIso);
  if (period === "undated") return !date;
  if (!date || date < today) return false;
  if (period === "month") return date.slice(0, 7) === today.slice(0, 7);
  // Calendar days in Rome, including today; daylight saving does not affect the interval.
  const difference = (Date.parse(`${date}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86_400_000;
  return difference >= 0 && difference < 7;
}

function normalized(value: string): string { return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("it"); }

export function filterEvents(events: HackEvent[], filters: EventFilters, savedIds: readonly string[], today: string): HackEvent[] {
  const words = normalized(filters.q.trim()).split(/\s+/).filter(Boolean);
  const saved = new Set(savedIds);
  return events.filter((event) => {
    const haystack = normalized(`${event.searchBlob} ${sourceLabel(event.source)}`);
    return words.every((word) => haystack.includes(word)) && matchesPeriod(event.dateIso, filters.period, today) && (filters.source === "all" || filters.source === event.source) && (!filters.saved || saved.has(event.id));
  }).sort((a, b) => filters.order === "name" ? a.title.localeCompare(b.title, "it") : (validEventDate(a.dateIso) || "9999-12-31").localeCompare(validEventDate(b.dateIso) || "9999-12-31") || a.title.localeCompare(b.title, "it"));
}

function calendarText(value: string): string { return value.replace(/\\/g, "\\\\").replace(/\r\n|\r|\n/g, "\\n").replace(/;/g, "\\;").replace(/,/g, "\\,"); }

function foldCalendarLine(line: string): string {
  const encoder = new TextEncoder();
  let result = "";
  let width = 0;
  for (const char of line) { const length = encoder.encode(char).length; if (width + length > 75) { result += "\r\n "; width = 1; } result += char; width += length; }
  return result;
}

export function eventCalendar(event: HackEvent, now = new Date()): string | null {
  const date = validEventDate(event.dateIso);
  if (!date) return null;
  const stamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  return [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Hackathon Milano//Eventi//IT", "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT", `UID:${calendarText(event.id)}@hackathon-milano`, `DTSTAMP:${stamp}`,
    `DTSTART;VALUE=DATE:${date.replace(/-/g, "")}`, `SUMMARY:${calendarText(event.title)}`,
    `DESCRIPTION:${calendarText(`${event.description}\n\nData di inizio dell’evento. Verifica orari, durata e iscrizione sul sito dell’organizzatore.\n${event.url}`)}`,
    `LOCATION:${calendarText(event.location)}`, `URL:${event.url.replace(/[\r\n]/g, "")}`,
    "END:VEVENT", "END:VCALENDAR",
  ].map(foldCalendarLine).join("\r\n") + "\r\n";
}
