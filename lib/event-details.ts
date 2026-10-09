import { REPO_URL, reviewedEvents, type HackEvent } from "./data";
import { todayInRome } from "./event-filters";
import type { EventRecord } from "./event-facts";

export interface EventDetail extends HackEvent {
  slug: string;
  detailPath: string;
  sourceLabel: string;
  checkedAt: string;
  dateLabel: string;
  endDateIso: string;
  organizer: string;
  facts: EventRecord["facts"];
  missing: string[];
  isPast: boolean;
  venue?: EventRecord["venue"];
}

function dateLabel(start: string, end: string): string {
  const format = (date: string) => new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Rome" }).format(new Date(`${date}T12:00:00Z`));
  return start === end ? format(start) : `${format(start)} – ${format(end)}`;
}

export function getEventDetails(): EventDetail[] {
  const today = todayInRome();
  return reviewedEvents.map((record) => ({
    id: record.id, slug: record.slug, detailPath: `/hackathon/${record.slug}`,
    title: record.title, url: record.url, source: "manual",
    sourceLabel: record.sourceLabel, checkedAt: record.checkedAt,
    dateStr: record.startDate, dateIso: record.startDate, endDateIso: record.endDate,
    dateVerified: true, dateLabel: dateLabel(record.startDate, record.endDate),
    day: String(Number(record.startDate.slice(8))),
    month: new Intl.DateTimeFormat("it-IT", { month: "short", timeZone: "Europe/Rome" }).format(new Date(`${record.startDate}T12:00:00Z`)).toUpperCase(),
    dateCompact: dateLabel(record.startDate, record.endDate),
    location: record.location, organizer: record.organizer,
    description: record.facts.slice(0, 2).map((fact) => `${fact.label}: ${fact.value}.`).join(" "),
    confidence: 0, reviewStatus: "source_checked", issueOk: "", issueDoubt: `${REPO_URL}/issues/new?${new URLSearchParams({ title: `[DUBBIO] ${record.title}`, body: `Scheda: /hackathon/${record.slug}\nFonte: ${record.url}\n\nInformazione da correggere:\n` })}`,
    searchBlob: `${record.title} ${record.location} ${record.organizer}`.toLowerCase(),
    facts: record.facts, missing: record.missing, venue: record.venue,
    isPast: record.endDate < today,
  })).sort((a, b) => a.dateIso.localeCompare(b.dateIso));
}

export function getEventDetail(slug: string): EventDetail | undefined {
  return getEventDetails().find((event) => event.slug === slug);
}
