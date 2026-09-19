// Run with: node scripts/test-frontend-data.mjs
// Exercise the frontend data boundary with an in-memory filesystem; never edit
// the collector dataset or depend on the date on the machine running the test.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

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

function loadData({ events = [], candidates = [], report } = {}) {
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

test("calendar dates are validated and past events use the Rome calendar day", () => {
  const { getSiteData } = loadData({ events: [
    event("yesterday", { date_str: "2026-09-18" }),
    event("today", { date_str: "2026-09-19" }),
    event("leap", { date_str: "2028-02-29T09:30:00+01:00" }),
    event("invalid-month", { date_str: "2026-13-01" }),
    event("invalid-day", { date_str: "2026-02-31" }),
    event("invalid-leap", { date_str: "2027-02-29" }),
    event("tbd", { date_str: "" }),
  ] });
  const results = Array.from(getSiteData().events);
  assert.ok(!results.some((entry) => entry.id === "yesterday"));
  assert.equal(results[0].id, "today");
  const leap = results.find((entry) => entry.id === "leap");
  assert.equal(leap.dateIso, "2028-02-29");
  assert.equal(leap.dateCompact, "29 feb 2028");
  for (const id of ["invalid-month", "invalid-day", "invalid-leap", "tbd"]) {
    const entry = results.find((candidate) => candidate.id === id);
    assert.equal(entry.dateIso, "", id);
    assert.equal(entry.day, "", id);
    assert.equal(entry.month, "", id);
  }
});

test("only actionable HTTP(S) source links reach either public collection", () => {
  const unsafeUrls = [
    "javascript:alert(1)", "data:text/html,<h1>event</h1>",
    "file:///tmp/event.html", "ftp://example.com/event", "mailto:organizer@example.com",
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
