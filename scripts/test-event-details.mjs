// Regression tests for manually sourced facts, stable event pages and SEO.
// No sources, archive files or real clock are modified by these tests.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

function loadModule(relativePath, dependencies = {}) {
  const source = fs.readFileSync(new URL(relativePath, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, {
    module, exports: module.exports, Date, Intl, URL, URLSearchParams,
    require(name) {
      if (Object.hasOwn(dependencies, name)) return dependencies[name];
      throw new Error(`Unexpected dependency: ${name}`);
    },
  }, { filename: relativePath });
  return module.exports;
}

const { validateEventRecords, safeSourceUrl, calendarDate, cleanEventDescription } = loadModule("../lib/event-facts.ts");
const { homeStructuredData, eventStructuredData, serializeStructuredData } = loadModule("../lib/seo.ts");
const origin = "https://hackathon-milano.vercel.app";

function record(overrides = {}) {
  return {
    id: "documented-event-id", slug: "documented-hackathon-2026",
    title: "Documented Hackathon 2026", url: "https://organizer.example/event",
    sourceLabel: "Official organizer", checkedAt: "2026-09-18",
    startDate: "2026-10-03", endDate: "2026-10-04", location: "Milano",
    organizer: "Example organizer",
    facts: [
      { label: "Audience", value: "University students", sourceUrl: "https://organizer.example/event" },
      { label: "Team", value: "Two to four participants", sourceUrl: "https://organizer.example/rules.pdf" },
      { label: "Cost", value: "Free", sourceUrl: "https://organizer.example/event" },
    ],
    missing: ["Exact venue", "Schedule"],
    ...overrides,
  };
}

function details(records) {
  return loadModule("../lib/event-details.ts", {
    "./data": { REPO_URL: "https://github.com/example/project", reviewedEvents: validateEventRecords(records) },
    "./event-filters": { todayInRome: () => "2026-10-03" },
  });
}

test("registry accepts sourced facts while explicitly preserving missing information", () => {
  const entry = record();
  const [result] = validateEventRecords([entry]);
  assert.equal(result, entry);
  assert.deepEqual(result.missing, ["Exact venue", "Schedule"]);
  assert.equal(result.venue, undefined);
});

test("registry rejects malformed identity, duplicate IDs and unstable slugs", () => {
  for (const value of [null, {}, "[]", [null], ["event"]]) {
    assert.throws(() => validateEventRecords(value));
  }
  for (const field of ["id", "title", "sourceLabel", "location", "organizer"]) {
    assert.throws(() => validateEventRecords([record({ [field]: " " })]), undefined, field);
  }
  for (const slug of ["", "Uppercase", "a/b", "two--hyphens", "-leading", "trailing-", "x".repeat(121)]) {
    assert.throws(() => validateEventRecords([record({ slug })]), undefined, slug);
  }
  assert.throws(() => validateEventRecords([record(), record({ slug: "another-edition" })]), /Duplicate/);
  assert.throws(() => validateEventRecords([record(), record({ id: "another-id" })]), /Duplicate/);
});

test("registry requires real ISO dates and rejects reversed or ambiguous event dates", () => {
  for (const checkedAt of ["2026-02-30", "2027-02-29", "2026-13-01", "2026-9-18", "18 settembre 2026", "2026-09-18T09:00:00Z", ""]) {
    assert.throws(() => validateEventRecords([record({ checkedAt })]), undefined, checkedAt);
  }
  for (const dates of [
    { startDate: "2026-02-30" }, { endDate: "2027-02-29" },
    { startDate: "2026-10-05", endDate: "2026-10-04" },
    { startDate: "2026-10-03T09:00:00Z" }, { endDate: "4 ottobre 2026" },
  ]) assert.throws(() => validateEventRecords([record(dates)]));
  assert.equal(validateEventRecords([record({ startDate: "2028-02-29", endDate: "2028-02-29" })]).length, 1);
});

test("sources must be HTTP(S) URLs without credentials for both the event and its facts", () => {
  for (const url of ["/event", "//organizer.example/event", "javascript:alert(1)", "data:text/html,test",
    "ftp://organizer.example/event", "https://user:secret@organizer.example/event", "https://user@organizer.example/event", "", null]) {
    assert.equal(safeSourceUrl(url), "", String(url));
    assert.throws(() => validateEventRecords([record({ url })]));
    const entry = record();
    entry.facts[0].sourceUrl = url;
    assert.throws(() => validateEventRecords([entry]));
  }
  assert.equal(safeSourceUrl(" https://organizer.example/event?x=1#details "), "https://organizer.example/event?x=1#details");
  assert.equal(safeSourceUrl("http://organizer.example/event"), "http://organizer.example/event");
});

test("pages require three complete facts and a complete documented venue when provided", () => {
  for (const facts of [[], record().facts.slice(0, 2), [null, null, null],
    [{ label: "Cost", value: "", sourceUrl: "https://organizer.example" }, ...record().facts]]) {
    assert.throws(() => validateEventRecords([record({ facts })]));
  }
  for (const missing of [null, "Schedule", [""]]) assert.throws(() => validateEventRecords([record({ missing })]));
  for (const venue of [{}, { name: "Venue" }, { name: "Venue", streetAddress: "Street 1", addressLocality: "Milano", addressCountry: "" }]) {
    assert.throws(() => validateEventRecords([record({ venue })]));
  }
  assert.equal(validateEventRecords([record({ missing: [], venue: {
    name: "Documented venue", streetAddress: "Street 1", addressLocality: "Milano", addressCountry: "IT",
  } })]).length, 1);
});

test("calendar parsing recognizes compact Italian dates and validates real calendar days", () => {
  assert.equal(calendarDate("21settembre2026"), "2026-09-21");
  assert.equal(calendarDate(" 21 Settembre 2026 "), "2026-09-21");
  assert.equal(calendarDate("2028-02-29T09:30:00+01:00"), "2028-02-29");
  for (const value of ["31aprile2026", "2027-02-29", "2026-13-01", "TBD", "", null, {}]) {
    assert.equal(calendarDate(value), "", String(value));
  }
});

test("description cleaning removes markup, embedded code and technical snippets without inventing text", () => {
  assert.equal(cleanEventDescription('<p>Build&nbsp;tools &amp; projects.</p><script>alert(1)</script><style>body { color: red }</style>'), "Build tools & projects.");
  for (const input of [null, {}, "", '<script type="application/ld+json">{"name":"Event"}</script>',
    '{"@context":"https://schema.org"}', '[{"name":"Event"}]', "speaker-area unknown template",
    "Skip to main content", "Salta al contenuto", "Accept all cookies", "Accetta tutti i cookie"]) {
    assert.equal(cleanEventDescription(input), "", String(input));
  }
});

test("past detail pages keep their URLs while ongoing events use their end date", () => {
  const { getEventDetails, getEventDetail } = details([
    record({ id: "past", slug: "past-edition-2026", startDate: "2026-09-01", endDate: "2026-09-02" }),
    record({ id: "ongoing", slug: "ongoing-edition-2026", startDate: "2026-10-02", endDate: "2026-10-03" }),
  ]);
  assert.equal(getEventDetails().length, 2);
  const past = getEventDetail("past-edition-2026");
  assert.equal(past.isPast, true);
  assert.equal(past.detailPath, "/hackathon/past-edition-2026");
  assert.equal(getEventDetail("ongoing-edition-2026").isPast, false);
  assert.equal(getEventDetail("unknown-edition"), undefined);
});

test("homepage structured data links reviewed entries to native pages and other entries to their source", () => {
  const data = homeStructuredData(origin, [
    { title: "Reviewed", url: "https://organizer.example/reviewed", detailPath: "/hackathon/reviewed-2026" },
    { title: "Collected", url: "https://organizer.example/collected" },
  ]);
  const list = data["@graph"].find((node) => node["@type"] === "CollectionPage").mainEntity;
  assert.equal(list.numberOfItems, 2);
  assert.equal(list.itemListElement[0].url, `${origin}/hackathon/reviewed-2026`);
  assert.equal(list.itemListElement[1].url, "https://organizer.example/collected");
  assert.equal(list.itemListElement[0].position, 1);
});

test("Event schema is only emitted for a documented venue and retains source citations", () => {
  const [withoutVenue] = details([record()]).getEventDetails();
  const plain = eventStructuredData(origin, withoutVenue);
  assert.ok(!plain["@graph"].some((node) => node["@type"] === "Event"));
  const page = plain["@graph"].find((node) => node["@type"] === "WebPage");
  assert.equal(page.dateModified, "2026-09-18");
  assert.deepEqual(Array.from(page.citation), ["https://organizer.example/event", "https://organizer.example/rules.pdf"]);
  const venue = { name: "Documented venue", streetAddress: "Street 1", addressLocality: "Milano", addressCountry: "IT" };
  const [withVenue] = details([record({ venue, missing: [] })]).getEventDetails();
  const graph = eventStructuredData(origin, withVenue)["@graph"];
  const event = graph.find((node) => node["@type"] === "Event");
  assert.equal(event.url, `${origin}/hackathon/documented-hackathon-2026`);
  assert.equal(event.location.address.streetAddress, venue.streetAddress);
  assert.equal(event.startDate, "2026-10-03");
  assert.equal(event.endDate, "2026-10-04");
  assert.equal(event.offers, undefined);
  assert.equal(event.eventStatus, undefined);
});

test("structured data serialization cannot close its script element", () => {
  const value = { name: '</script><script>alert("unsafe")</script>' };
  const serialized = serializeStructuredData(value);
  assert.ok(!serialized.includes("<"));
  assert.deepEqual(JSON.parse(serialized), value);
});

test("versioned registry and exclusions contain valid public review records", () => {
  const registry = JSON.parse(fs.readFileSync(new URL("../data/event_details.json", import.meta.url), "utf8"));
  const exclusions = JSON.parse(fs.readFileSync(new URL("../data/event_exclusions.json", import.meta.url), "utf8"));
  validateEventRecords(registry);
  assert.ok(Array.isArray(exclusions));
  const seen = new Set();
  for (const entry of exclusions) {
    assert.ok(typeof entry.id === "string" && entry.id.trim());
    assert.ok(!seen.has(entry.id));
    assert.ok(typeof entry.reason === "string" && entry.reason.trim());
    assert.ok(safeSourceUrl(entry.sourceUrl));
    assert.ok(calendarDate(entry.checkedAt));
    assert.equal(entry.checkedAt, calendarDate(entry.checkedAt));
    seen.add(entry.id);
  }
});
