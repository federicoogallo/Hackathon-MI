// Run with: node scripts/test-frontend-data.mjs
// Exercise the frontend data boundary with an in-memory filesystem; never edit
// the collector dataset or depend on the date on the machine running the test.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const factsSource = fs.readFileSync(new URL("../lib/event-facts.ts", import.meta.url), "utf8");
const factsCode = ts.transpileModule(factsSource, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
}).outputText;
const eventFacts = await import(`data:text/javascript;base64,${Buffer.from(factsCode).toString("base64")}`);

const source = fs.readFileSync(new URL("../lib/data.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS,
    esModuleInterop: true,
  },
}).outputText;

// It is September 19 in Rome while it is still September 18 in UTC.
const now = "2026-09-18T22:30:00Z";
class FixedDate extends Date {
  constructor(...args) {
    super(...(args.length ? args : [now]));
  }
  static now() { return new Date(now).getTime(); }
}

function loadData({ events = [], candidates = [], report, reviewed = [], exclusions = [] } = {}) {
  const dataRoot = path.join("/virtual", "frontend", "data");
  const files = new Map([
    [path.join(dataRoot, "events.json"), JSON.stringify({
      last_check: "2026-09-18T16:48:09+02:00",
      events,
    })],
    [path.join(dataRoot, "review_queue.json"), JSON.stringify({ candidates })],
  ]);
  if (report) files.set(path.join(dataRoot, "last_report.json"), JSON.stringify(report));
  const mockFs = {
    existsSync: (file) => files.has(file),
    readFileSync(file) {
      if (!files.has(file)) throw new Error(`Missing fixture: ${file}`);
      return files.get(file);
    },
  };
  const module = { exports: {} };
  vm.runInNewContext(compiled, {
    module,
    exports: module.exports,
    require(name) {
      if (name === "node:fs") return mockFs;
      if (name === "node:path") return path;
      if (name === "./event-facts") return eventFacts;
      if (name === "@/data/event_details.json") return reviewed;
      if (name === "@/data/event_exclusions.json") return exclusions;
      throw new Error(`Unexpected dependency: ${name}`);
    },
    process: { cwd: () => path.join("/virtual", "frontend"), env: {} },
    Date: FixedDate,
    Intl,
    URL,
    URLSearchParams,
  }, { filename: "lib/data.ts" });
  return module.exports;
}

function event(id, overrides = {}) {
  return {
    id,
    title: `Hackathon ${id}`,
    url: `https://example.com/events/${id}`,
    date_str: "2026-10-03",
    is_hackathon: true,
    description: "Build a project in Milano.",
    source: "web_search",
    location: "Milano",
    confidence: 0.9,
    ...overrides,
  };
}

function reviewedEvent(id, overrides = {}) {
  return {
    id,
    slug: `hackathon-${id}`,
    title: `Reviewed hackathon ${id}`,
    url: `https://organizer.example/events/${id}`,
    sourceLabel: "Official organizer",
    checkedAt: "2026-09-18",
    startDate: "2026-10-03",
    endDate: "2026-10-03",
    location: "Documented venue, Milano",
    organizer: "Event organizer",
    facts: ["Format", "Audience", "Teams"].map((label) => ({
      label, value: `Documented ${label.toLowerCase()}`,
      sourceUrl: `https://organizer.example/events/${id}`,
    })),
    missing: ["Exact schedule"],
    ...overrides,
  };
}

test("search finds information beyond the compact card excerpt", () => {
  const description = `${"Descrizione evento per chi vuole partecipare. ".repeat(9)}Google Arena, Isola; aperto ai maggiorenni.`;
  const { getSiteData } = loadData({ events: [event("long", { description })] });
  const [result] = getSiteData().events;
  assert.ok(result.description.length <= 213);
  assert.ok(result.description.endsWith("..."));
  assert.ok(!result.description.includes("Google Arena"));
  assert.ok(result.searchBlob.includes("google arena, isola"));
  assert.ok(result.searchBlob.includes("maggiorenni"));
});

test("only reviewed dates are displayed; raw dates still suppress past events in Rome", () => {
  const { getSiteData } = loadData({ events: [
    event("yesterday", { date_str: "2026-09-18" }),
    event("italian-past", { date_str: "18settembre2026" }),
    event("today", { date_str: "2026-09-19" }),
    event("leap", { date_str: "2028-02-29T09:30:00+01:00" }),
    event("raw-future", { date_str: "2026-12-01" }),
    event("invalid-month", { date_str: "2026-13-01" }),
    event("invalid-day", { date_str: "2026-02-31" }),
    event("invalid-leap", { date_str: "2027-02-29" }),
    event("tbd", { date_str: "" }),
  ], reviewed: [
    reviewedEvent("today", { startDate: "2026-09-19", endDate: "2026-09-19" }),
    reviewedEvent("leap", { startDate: "2028-02-29", endDate: "2028-02-29" }),
  ] });
  const results = Array.from(getSiteData().events);
  assert.ok(!results.some((entry) => ["yesterday", "italian-past"].includes(entry.id)));
  assert.equal(results[0].id, "today");
  const leap = results.find((entry) => entry.id === "leap");
  assert.equal(leap.dateIso, "2028-02-29");
  assert.equal(leap.dateCompact, "29 feb 2028");
  assert.equal(leap.dateVerified, true);
  for (const id of ["raw-future", "invalid-month", "invalid-day", "invalid-leap", "tbd"]) {
    const entry = results.find((candidate) => candidate.id === id);
    assert.equal(entry.dateIso, "", id);
    assert.equal(entry.dateStr, "", id);
    assert.equal(entry.day, "", id);
    assert.equal(entry.month, "", id);
    assert.equal(entry.endDateIso, "", id);
    assert.equal(entry.dateCompact, "Data da verificare", id);
    assert.equal(entry.dateVerified, false, id);
    assert.equal(entry.detailPath, undefined, id);
  }
});

test("only actionable HTTP(S) source links reach either public collection", () => {
  const unsafeUrls = [
    "javascript:alert(1)", "data:text/html,<h1>event</h1>",
    "file:///tmp/event.html", "ftp://example.com/event", "mailto:organizer@example.com",
    "https://user:secret@example.com/event", "https://user@example.com/event",
    "/relative/event", "//example.com/event", "#", "", null, { href: "https://example.com" },
  ];
  const records = [
    event("https", { url: " https://example.com/confirmed?track=1#details " }),
    event("http", { url: "http://example.com/legacy" }),
    ...unsafeUrls.map((url, i) => event(`unsafe-${i}`, { url })),
  ];
  const { getSiteData, getReviewData } = loadData({ events: records, candidates: [...records, null] });
  const site = getSiteData();
  const review = getReviewData();
  assert.deepEqual(Array.from(site.events, (entry) => entry.id), ["https", "http"]);
  assert.deepEqual(Array.from(review.candidates, (entry) => entry.id), ["https", "http"]);
  assert.equal(site.reviewCount, review.candidates.length);
  assert.equal(site.events[0].url, "https://example.com/confirmed?track=1#details");
  assert.equal(review.candidates[0].url, site.events[0].url);
  for (const entry of [...site.events, ...review.candidates]) {
    assert.ok(["http:", "https:"].includes(new URL(entry.url).protocol));
    assert.equal(new URL(entry.issueDoubt).origin, "https://github.com");
  }
});

test("object archives remain supported and stale failure reports do not override a later scan", () => {
  const { getSiteData } = loadData({
    events: { first: event("object-record"), ignored: event("other", { is_hackathon: false }) },
    report: { date: "2026-05-03 13:41", status: "llm_failed_preserved", failed_collectors: [] },
  });
  const result = getSiteData();
  assert.equal(result.events.length, 1);
  assert.equal(result.events[0].id, "object-record");
  assert.equal(result.statusOk, true);
  assert.equal(result.lastScan, "18 set 2026 alle 16:48");
});

test("reviewed information overrides stale collected details and keeps ongoing events", () => {
  const curated = reviewedEvent("ongoing", { startDate: "2026-09-18", endDate: "2026-09-20" });
  const { getSiteData } = loadData({
    events: [event("ongoing", {
      title: "Old title", date_str: "2025-01-01", location: "Unverified location",
      description: "Generated unsupported claim", url: "https://example.com/old",
    })],
    reviewed: [curated],
  });
  const [result] = getSiteData().events;
  assert.equal(result.title, curated.title);
  assert.equal(result.location, curated.location);
  assert.equal(result.url, curated.url);
  assert.equal(result.dateIso, "2026-09-18");
  assert.equal(result.endDateIso, "2026-09-20");
  assert.equal(result.detailPath, `/hackathon/${curated.slug}`);
  assert.ok(result.description.includes("Documented format"));
  assert.ok(!result.description.includes("unsupported"));
  assert.ok(!result.searchBlob.includes("unsupported"));
});

test("exclusions, rejections and completed reviewed events stay out of the calendar", () => {
  const { getSiteData } = loadData({
    events: [event("excluded"), event("rejected", { review_status: "manual_rejected" }),
      event("also-rejected", { review_status: "rejected" }), event("ended"), event("eligible")],
    exclusions: [{ id: "excluded", reason: "Retrospective report", sourceUrl: "https://example.com/report", checkedAt: "2026-09-18" }],
    reviewed: [reviewedEvent("ended", { startDate: "2026-09-01", endDate: "2026-09-18" })],
  });
  assert.deepEqual(Array.from(getSiteData().events, (entry) => entry.id), ["eligible"]);
});

test("missing locations are not invented in the calendar or review queue", () => {
  const record = event("missing-place", { location: "" });
  const { getSiteData, getReviewData } = loadData({ events: [record], candidates: [record] });
  assert.equal(getSiteData().events[0].location, "");
  assert.equal(getReviewData().candidates[0].location, "");
});

test("invalid reviewed registry data fails before pages can be generated", () => {
  assert.throws(() => loadData({ reviewed: [reviewedEvent("invalid", { facts: [] })] }), /sourced facts/);
});
