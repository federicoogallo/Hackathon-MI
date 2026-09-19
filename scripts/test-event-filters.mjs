// Run with: node scripts/test-event-filters.mjs
// Fixed calendar dates exercise user-visible boundaries without depending on
// the machine timezone, the collector data, or the day the tests are run.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../lib/event-filters.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;
const module = { exports: {} };
vm.runInNewContext(compiled, {
  module, exports: module.exports, Date, Intl, URL, URLSearchParams, TextEncoder,
  require(name) { throw new Error(`Client filter helpers must not import runtime server data: ${name}`); },
}, { filename: "lib/event-filters.ts" });
const { DEFAULT_EVENT_FILTERS, readEventFilters, writeEventFilters, validEventDate,
  todayInRome, matchesPeriod, filterEvents, eventCalendar, sourceLabel } = module.exports;

function event(id, overrides = {}) {
  const record = { id, title: `Hackathon ${id}`, url: `https://example.com/${id}`, source: "web_search",
    dateIso: "2026-09-19", dateStr: "2026-09-19", day: "19", month: "SET", dateCompact: "19 set 2026",
    location: "Milano", description: "Un laboratorio di creatività con dati aperti.", confidence: .9,
    reviewStatus: "ai_verified", issueOk: "https://example.com/ok", issueDoubt: "https://example.com/doubt", ...overrides };
  return { searchBlob: `${record.title} ${record.description} ${record.location} ${record.source}`.toLowerCase(), ...record };
}

test("Rome day changes at local midnight in summer and winter", () => {
  assert.equal(todayInRome(new Date("2026-09-18T22:30:00Z")), "2026-09-19");
  assert.equal(todayInRome(new Date("2026-12-31T23:15:00Z")), "2027-01-01");
  assert.equal(todayInRome(new Date("2026-03-28T23:30:00Z")), "2026-03-29");
});

test("next seven days includes today through day six across daylight saving and year boundaries", () => {
  for (const [today, last, outside] of [
    ["2026-03-26", "2026-04-01", "2026-04-02"],
    ["2026-10-23", "2026-10-29", "2026-10-30"],
    ["2026-12-29", "2027-01-04", "2027-01-05"],
  ]) {
    assert.equal(matchesPeriod(today, "week", today), true);
    assert.equal(matchesPeriod(last, "week", today), true);
    assert.equal(matchesPeriod(outside, "week", today), false);
    const yesterday = new Date(`${today}T00:00:00Z`);
    yesterday.setUTCDate(yesterday.getUTCDate() - 1);
    assert.equal(matchesPeriod(yesterday.toISOString().slice(0, 10), "week", today), false);
  }
});

test("month filters show only remaining dates this calendar month and undated is distinct", () => {
  assert.equal(matchesPeriod("2026-09-19", "month", "2026-09-19"), true);
  assert.equal(matchesPeriod("2026-09-30", "month", "2026-09-19"), true);
  assert.equal(matchesPeriod("2026-09-18", "month", "2026-09-19"), false);
  assert.equal(matchesPeriod("2026-10-01", "month", "2026-09-19"), false);
  assert.equal(matchesPeriod("2027-09-20", "month", "2026-09-19"), false);
  assert.equal(matchesPeriod("", "undated", "2026-09-19"), true);
  assert.equal(matchesPeriod("", "week", "2026-09-19"), false);
  assert.equal(matchesPeriod("2026-09-20", "undated", "2026-09-19"), false);
});

test("invalid dates do not acquire a misleading calendar date", () => {
  for (const invalid of ["2026-02-29", "2026-02-31", "2026-13-01", "2026-00-10", "TBD", "", "2026-09-19T12:00:00Z"]) {
    assert.equal(validEventDate(invalid), null, invalid);
    assert.equal(eventCalendar(event("bad-date", { dateIso: invalid })), null, invalid);
  }
  assert.equal(validEventDate("2028-02-29"), "2028-02-29");
});

test("search ignores accents and combines words, readable sources and saved filters", () => {
  const records = [
    event("matching", { title: "Creatività con dati", source: "web_search" }),
    event("other-source", { title: "Creatività con dati", source: "eventbrite" }),
    event("not-saved", { title: "Creatività con dati" }),
    event("no-match", { title: "Sport", description: "Calcio a Milano" }),
  ];
  const filters = { ...DEFAULT_EVENT_FILTERS, q: "  DATI creativita  ", source: "web_search", saved: true };
  assert.deepEqual(Array.from(filterEvents(records, filters, ["matching", "other-source", "no-match"], "2026-09-19"), (entry) => entry.id), ["matching"]);
  assert.equal(filterEvents(records, { ...DEFAULT_EVENT_FILTERS, q: "ricerca web" }, [], "2026-09-19").length, 3);
  assert.equal(filterEvents(records, { ...DEFAULT_EVENT_FILTERS, q: "inesistente" }, [], "2026-09-19").length, 0);
});

test("nearest date order puts unknown dates last and name order uses the Italian alphabet", () => {
  const records = [event("late", { title: "Alfa", dateIso: "2026-11-01" }), event("undated", { title: "Beta", dateIso: "" }), event("early", { title: "Zeta", dateIso: "2026-10-01" })];
  assert.deepEqual(Array.from(filterEvents(records, DEFAULT_EVENT_FILTERS, [], "2026-09-19"), (entry) => entry.id), ["early", "late", "undated"]);
  assert.deepEqual(Array.from(filterEvents(records, { ...DEFAULT_EVENT_FILTERS, order: "name" }, [], "2026-09-19"), (entry) => entry.id), ["late", "undated", "early"]);
});

test("URL filters round trip, sanitize unknown modes and preserve unrelated parameters and anchors", () => {
  const filters = { q: "AI & dati", period: "week", source: "web_search", saved: true, order: "name", view: "list" };
  const result = writeEventFilters(new URL("https://example.com/?utm_campaign=milano#events"), filters);
  const url = new URL(result, "https://example.com");
  assert.equal(url.searchParams.get("utm_campaign"), "milano");
  assert.equal(url.hash, "#events");
  assert.deepEqual(JSON.parse(JSON.stringify(readEventFilters(url.search))), filters);
  assert.deepEqual(JSON.parse(JSON.stringify(readEventFilters("?period=invalid&order=random&view=invalid&saved=yes"))), JSON.parse(JSON.stringify(DEFAULT_EVENT_FILTERS)));
  const cleared = writeEventFilters(url, DEFAULT_EVENT_FILTERS);
  assert.equal(cleared, "/?utm_campaign=milano#events");
});

test("calendar download contains only a start date and safely folds UTF-8 and escapes text", () => {
  const record = event("calendar", { title: "Caffè, dati; idee\\future\nseconda riga", location: "Milano; Italia", description: "È un’attività: ".repeat(24) });
  const calendar = eventCalendar(record, new Date("2026-09-19T14:30:42.456Z"));
  assert.ok(calendar.endsWith("END:VCALENDAR\r\n"));
  const unfolded = calendar.replace(/\r\n /g, "");
  assert.ok(unfolded.includes("DTSTART;VALUE=DATE:20260919\r\n"));
  assert.ok(unfolded.includes("DTSTAMP:20260919T143042Z\r\n"));
  assert.ok(!unfolded.includes("DTEND") && !unfolded.includes("DTSTART;TZID"));
  assert.ok(unfolded.includes("SUMMARY:Caffè\\, dati\\; idee\\\\future\\nseconda riga\r\n"));
  assert.ok(unfolded.includes("LOCATION:Milano\\; Italia\r\n"));
  assert.ok(unfolded.includes("Data di inizio dell’evento."));
  assert.ok(unfolded.includes("Verifica orari\\, durata e iscrizione"));
  for (const line of calendar.split("\r\n")) assert.ok(Buffer.byteLength(line, "utf8") <= 75, `Calendar line exceeds 75 octets: ${line}`);
  assert.ok(!calendar.includes("\uFFFD"), "UTF-8 folding must not split a character");
});

test("sources are readable without inventing verification claims", () => {
  assert.equal(sourceLabel("web_search"), "Ricerca web");
  assert.equal(sourceLabel("community_feed"), "Community feed");
  assert.equal(sourceLabel(""), "Fonte esterna");
});
