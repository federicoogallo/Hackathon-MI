import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const PREFIX = "hackathon-mi:newsletter:brevo:";
const baseEvent = { id: "event-one", title: "Una sfida", url: "https://organizer.test/event", is_hackathon: true, review_status: "ai_verified", date_str: "2026-10-01", discovered_at: "2026-09-17T12:00:00Z", location: "Milano" };

function harness(options = {}) {
  let now = Date.parse(options.now || "2026-09-21T08:30:00Z");
  const env = {
    NEWSLETTER_ENABLED: "true", BREVO_API_KEY: "test-api", BREVO_LIST_ID: "12",
    NEWSLETTER_FROM: "news@example.test", NEWSLETTER_CONTACT_EMAIL: "hello@example.test",
    NEWSLETTER_OWNER: "Test owner", UPSTASH_REDIS_REST_URL: "https://redis.test", UPSTASH_REDIS_REST_TOKEN: "test-redis",
    CRON_SECRET: "a-test-secret-with-at-least-32-characters", NODE_ENV: "production", VERCEL: "1", ...options.env,
  };
  class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : [now])); }
    static now() { return now; }
  }
  const store = new Map();
  const calls = [];
  const campaigns = new Map();
  const contacts = new Map(options.contacts || []);
  let providerFailure = options.providerFailure;
  const get = key => {
    const entry = store.get(key);
    if (entry?.expires && entry.expires <= now) { store.delete(key); return null; }
    return entry?.value ?? null;
  };
  const set = (key, value, ttl) => { store.set(key, { value, expires: ttl ? now + Number(ttl) * 1000 : null }); return "OK"; };
  function command(args) {
    const [op, ...values] = args;
    if (op === "GET") return get(values[0]);
    if (op === "SET") {
      const [key, value, ...flags] = values;
      if (flags.includes("NX") && get(key) !== null) return null;
      return set(key, value, flags.includes("EX") ? flags[flags.indexOf("EX") + 1] : null);
    }
    if (op === "MGET") return values.map(get);
    if (op !== "EVAL") throw new Error(`Unexpected command: ${op}`);
    const [script, count, ...rest] = values;
    const keys = rest.slice(0, count);
    const argv = rest.slice(count);
    if (script.includes("'ZREMRANGEBYSCORE'")) {
      const entries = new Map(get(keys[0]) || []);
      for (const [id, time] of entries) if (time <= Number(argv[0])) entries.delete(id);
      if (entries.size >= Number(argv[1])) return 0;
      entries.set(argv[3], Number(argv[2])); set(keys[0], [...entries], argv[4]); return 1;
    }
    if (script.includes("math.max")) {
      let n = Math.max(Number(get(keys[0]) || 0), Number(argv[0])); set(keys[0], n);
      if (get(keys[1])) return 1;
      if (Number(argv[2]) === 1) { if (n >= Number(argv[1])) return 0; n++; }
      set(keys[0], n); set(keys[1], "1"); return 1;
    }
    if (script.includes("'INCR'")) { const n = Number(get(keys[0]) || 0) + 1; const expiry = store.get(keys[0])?.expires; set(keys[0], n, argv[0]); if (n > 1) store.get(keys[0]).expires = expiry; return n; }
    if (script.startsWith("if redis.call('GET'")) { if (get(keys[0]) === argv[0]) { store.delete(keys[0]); return 1; } return 0; }
    if (script.includes("#KEYS")) { set(keys[0], argv[0]); store.delete(keys[1]); keys.slice(2).forEach(key => set(key, "1")); return 1; }
    if (count === 3) { set(keys[0], "1", argv[0]); set(keys[1], argv[1], argv[2]); store.delete(keys[2]); return 1; }
    if (count === 2) { set(keys[0], argv[0]); set(keys[1], argv[1]); return 1; }
    throw new Error("Unexpected Redis script");
  }
  const mockedFetch = async (url, init = {}) => {
    const payload = init.body ? JSON.parse(init.body) : undefined;
    if (url === "https://redis.test") return Response.json({ result: command(payload) });
    assert.ok(String(url).startsWith("https://api.brevo.com/v3/"), "Tests cannot contact a real service");
    const path = new URL(url).pathname.slice(3);
    const method = init.method || "GET";
    calls.push({ path, method, payload, headers: init.headers });
    if (providerFailure) {
      const failure = providerFailure({ path, method, payload });
      if (failure === "timeout") throw new Error("Simulated timeout with private test address");
      if (typeof failure === "number") return Response.json({ message: "provider-private@example.test" }, { status: failure });
    }
    if (path === "/account") return Response.json(options.account || { plan: [{ type: "free", creditsType: "sendLimit", credits: options.credits ?? 300 }], relay: { enabled: true } });
    if (path === "/smtp/email") return Response.json({ messageId: "email-one" });
    if (path === "/contacts/lists/12") return Response.json({ id: 12, totalSubscribers: options.audience ?? [...contacts.values()].filter(c => c.listIds?.includes(12)).length });
    if (path === "/contacts" && method === "POST") {
      if (contacts.has(payload.email)) return Response.json({ code: "duplicate_parameter" }, { status: 400 });
      contacts.set(payload.email, { email: payload.email, emailBlacklisted: false, listIds: payload.listIds }); return Response.json({ id: contacts.size }, { status: 201 });
    }
    if (path.startsWith("/contacts/") && method === "GET") { const contact = contacts.get(decodeURIComponent(path.slice(10))); return Response.json(contact || {}, { status: contact ? 200 : 404 }); }
    if (path === "/emailCampaigns" && method === "POST") { const id = campaigns.size + 1; campaigns.set(id, { id, status: "draft", ...payload }); return Response.json({ id }, { status: 201 }); }
    if (path.endsWith("/sendNow")) { campaigns.get(Number(path.split("/")[2])).status = options.sentStatus || "sent"; return new Response(null, { status: 204 }); }
    if (path.startsWith("/emailCampaigns/")) return Response.json(campaigns.get(Number(path.split("/")[2])) || {}, { status: campaigns.has(Number(path.split("/")[2])) ? 200 : 404 });
    throw new Error(`Unhandled provider route: ${path}`);
  };
  const cache = new Map();
  function load(name) {
    if (cache.has(name)) return cache.get(name);
    const source = fs.readFileSync(new URL(`../lib/${name}.ts`, import.meta.url), "utf8");
    const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, esModuleInterop: true } }).outputText;
    const module = { exports: {} };
    const require = path => {
      if (path === "node:crypto") return crypto;
      if (path === "./data") return { SITE_URL: options.siteUrl || "https://example.test" };
      if (path === "../data/events.json") return { events: options.events || [baseEvent] };
      if (path.startsWith("./newsletter")) return load(path.slice(2));
      throw new Error(`Unexpected import: ${path}`);
    };
    vm.runInNewContext(compiled, { module, exports: module.exports, require, process: { env }, fetch: mockedFetch, Request, Response, Buffer, AbortSignal, TextDecoder, Uint8Array, URL, Date: Clock, Intl }, { filename: `lib/${name}.ts` });
    cache.set(name, module.exports);
    return module.exports;
  }
  const api = load("newsletter");
  const core = load("newsletter-core");
  const request = (body, extra = {}) => new Request("https://example.test/api/newsletter/subscribe", {
    method: "POST", headers: { "Content-Type": "application/json", Origin: "https://example.test", "x-forwarded-for": "192.0.2.1", ...extra.headers }, body: typeof body === "string" ? body : JSON.stringify(body),
  });
  const signup = (email = "reader@example.test", extra = {}) => api.subscribe(request({ email, consent: true, website: "" }, extra));
  const token = () => calls.findLast(call => call.path === "/smtp/email")?.payload.textContent.match(/#token=([a-f0-9]{64})/)[1];
  const confirm = value => api.confirm(request({ token: value || token() }));
  const weekly = authorization => api.weekly(new Request("https://example.test/api/newsletter/weekly", { headers: { authorization: authorization ?? `Bearer ${env.CRON_SECRET}` } }));
  return { api, core, env, calls, campaigns, contacts, store, get, set, request, signup, token, confirm, weekly, fail: fn => { providerFailure = fn; }, advance: milliseconds => { now += milliseconds; } };
}

test("readiness fails closed and cron authorization never reaches providers", async () => {
  for (const env of [{ NEWSLETTER_ENABLED: "false" }, { BREVO_API_KEY: "" }, { CRON_SECRET: "short" }, { NEWSLETTER_CONTACT_EMAIL: "invalid" }]) {
    const h = harness({ env });
    assert.equal((await h.signup()).status, 503);
    assert.equal(h.calls.length, 0);
  }
  const h = harness();
  assert.equal((await h.weekly("Bearer wrong")).status, 401);
  assert.equal((await h.weekly("")).status, 401);
  assert.equal(h.calls.length, 0);
  assert.equal(h.store.size, 0);
});

test("signup enforces origin, consent, bounded JSON and email headers before sending", async () => {
  const h = harness();
  assert.equal((await h.signup("person@example.test", { headers: { Origin: "https://attacker.test" } })).status, 403);
  assert.equal((await h.api.subscribe(h.request({ email: "person@example.test", consent: false }))).status, 400);
  assert.equal((await h.signup("person@example.test\r\nBcc: injected@example.test")).status, 400);
  assert.equal((await h.api.subscribe(h.request("x".repeat(4097)))).status, 413);
  assert.equal((await h.api.subscribe(h.request("{}", { headers: { "Content-Type": "badapplication/json" } }))).status, 415);
  assert.equal((await h.api.subscribe(h.request("{"))).status, 400);
  assert.equal((await h.api.subscribe(h.request({ website: "bot" }))).status, 202);
  assert.equal(h.calls.length, 0);
});

test("double opt-in stores only a hashed token, consumes it once and retains minimal consent", async () => {
  const h = harness();
  const response = await h.signup();
  assert.equal(response.status, 202);
  assert.equal(response.headers.get("cache-control"), "no-store");
  const token = h.token();
  assert.match(token, /^[a-f0-9]{64}$/);
  assert.ok([...h.store.keys()].every(key => !key.includes(token) && !key.includes("reader@example.test")));
  assert.equal(h.calls.filter(call => call.path.startsWith("/contacts")).length, 0);
  assert.equal((await h.confirm(token)).status, 200);
  assert.equal((await h.confirm(token)).status, 200);
  assert.equal(h.calls.filter(call => call.path === "/contacts" && call.method === "POST").length, 1);
  assert.ok(![...h.store.keys()].some(key => key.includes(":pending:")));
  const evidence = [...h.store.entries()].find(([key]) => key.includes(":consent:"));
  assert.ok(evidence);
  assert.ok(!evidence[1].value.includes("reader@example.test"));
  assert.equal(JSON.parse(evidence[1].value).version, "2026-09-24");
});

test("pending confirmations expire, provider errors are redacted and recoverable", async () => {
  const h = harness();
  await h.signup();
  const token = h.token();
  h.fail(({ path }) => path === "/contacts" ? 503 : undefined);
  const failed = await h.confirm(token);
  assert.equal(failed.status, 503);
  assert.ok(!(await failed.text()).includes("provider-private"));
  assert.ok([...h.store.keys()].some(key => key.includes(":pending:")));
  h.fail(undefined);
  assert.equal((await h.confirm(token)).status, 200);
  const expired = harness();
  await expired.signup();
  const oldToken = expired.token();
  expired.advance(86401_000);
  assert.equal((await expired.confirm(oldToken)).status, 410);
  assert.equal(expired.calls.filter(call => call.path.startsWith("/contacts")).length, 0);
});

test("resubscription cannot silently reactivate a globally unsubscribed contact", async () => {
  const h = harness({ contacts: [["reader@example.test", { email: "reader@example.test", emailBlacklisted: true }]] });
  await h.signup();
  assert.equal((await h.confirm()).status, 409);
  assert.ok(!h.calls.some(call => call.path.startsWith("/contacts") && call.method !== "GET"));
  assert.equal(h.contacts.get("reader@example.test").emailBlacklisted, true);
});

test("persistent quotas block repeated emails and IP abuse", async () => {
  const h = harness();
  assert.equal((await h.signup()).status, 202);
  assert.equal((await h.signup()).status, 202);
  assert.equal(h.calls.filter(call => call.path === "/smtp/email").length, 1);
  for (let index = 0; index < 3; index++) assert.equal((await h.signup(`reader${index}@example.test`)).status, 202);
  assert.equal((await h.signup("sixth@example.test")).status, 429);
  const quota = harness();
  quota.set(`${PREFIX}confirmation-quota`, Array.from({ length: 40 }, (_, i) => [`confirmation-${i}`, Date.parse("2026-09-21T08:00:00Z")]), 86400);
  assert.equal((await quota.signup()).status, 429);
  assert.equal(quota.calls.length, 0);
});

test("weekly windows remain Monday08 UTC across DST and delayed invocations", () => {
  const { core } = harness();
  for (const [when, start, end] of [
    ["2026-09-21T08:00:00Z", "2026-09-14T08:00:00.000Z", "2026-09-21T08:00:00.000Z"],
    ["2026-09-23T11:00:00Z", "2026-09-14T08:00:00.000Z", "2026-09-21T08:00:00.000Z"],
    ["2026-10-26T08:30:00Z", "2026-10-19T08:00:00.000Z", "2026-10-26T08:00:00.000Z"],
    ["2026-09-21T07:59:59Z", "2026-09-07T08:00:00.000Z", "2026-09-14T08:00:00.000Z"],
  ]) {
    const window = core.weeklyWindow(new Date(when));
    assert.equal(window.start.toISOString(), start);
    assert.equal(window.end.toISOString(), end);
  }
});

test("digest excludes stale, unsafe, unconfirmed and already-outside-window events", () => {
  const { core } = harness();
  const changes = [
    { id: "start", discovered_at: "2026-09-14T08:00:00Z" },
    { id: "end", discovered_at: "2026-09-21T08:00:00Z" },
    { id: "past", date_str: "2026-09-20" },
    { id: "european-past", date_str: "20/09/2026" },
    { id: "european-future", date_str: "01/10/2026" },
    { id: "invalid-date", date_str: "2026-02-30" },
    { id: "unrecognized-date", date_str: "October sometime" },
    { id: "unsafe", url: "javascript:alert(1)" },
    { id: "rejected", review_status: "manual_rejected" },
    { id: "pending", review_status: "ai_pending" },
    { id: "not-hackathon", is_hackathon: false },
    { id: "old", discovered_at: "2026-08-01T10:00:00Z" },
    { id: "newly-reviewed", discovered_at: "2026-08-01T10:00:00Z", reviewed_at: "2026-09-18T10:00:00+02:00" },
    { id: "undated", date_str: "TBD" },
    { id: "legacy", discovered_at: "2026-09-18T10:00:00.123456" },
  ];
  const result = core.selectDigestEvents({ events: changes.map(change => ({ ...baseEvent, ...change })) }, new Date("2026-09-21T08:30:00Z"));
  assert.deepEqual(Array.from(result, event => event.id).sort(), ["european-future", "legacy", "newly-reviewed", "start", "undated"]);
});

test("email rendering escapes untrusted content and includes provider unsubscribe in both formats", () => {
  const { core } = harness();
  const email = core.digestEmail([{ id: "e", title: '<img src=x onerror="bad">', url: "https://example.test/?a=1&b=2", date: "", location: "<Milano>" }], "https://example.test", "Owner <script>", "hello@example.test");
  assert.ok(!email.html.includes("<img"));
  assert.ok(email.html.includes("&lt;img"));
  assert.ok(email.html.includes("&amp;b=2"));
  assert.ok(email.html.includes("&lt;Milano&gt;"));
  assert.ok(email.html.includes("{{ unsubscribe }}"));
  assert.ok(email.text.includes("{{ unsubscribe }}"));
  assert.ok(email.text.includes("Data da confermare"));
});

test("weekly delivery drafts then sends once, persists event IDs and skips empty weeks", async () => {
  const h = harness({ audience: 1 });
  assert.equal((await h.weekly()).status, 200);
  assert.equal((await h.weekly()).status, 200);
  assert.equal(h.calls.filter(call => call.path === "/emailCampaigns" && call.method === "POST").length, 1);
  assert.equal(h.calls.find(call => call.path === "/emailCampaigns").payload.scheduledAt, undefined);
  assert.deepEqual(h.calls.find(call => call.path === "/emailCampaigns").payload.recipients, { listIds: [12] });
  assert.equal(h.calls.filter(call => call.path.endsWith("/sendNow")).length, 1);
  assert.ok([...h.store.keys()].some(key => key.includes(":sent-event:")));
  assert.equal(h.get(`${PREFIX}weekly-active`), null);
  const empty = harness({ events: [] });
  assert.equal((await (await empty.weekly()).json()).status, "empty");
  assert.equal(empty.calls.length, 0);
});

test("ambiguous campaign creation fails closed instead of creating another campaign", async () => {
  const h = harness({ audience: 1, providerFailure: ({ path, method }) => path === "/emailCampaigns" && method === "POST" ? "timeout" : undefined });
  assert.equal((await h.weekly()).status, 503);
  h.fail(undefined);
  assert.equal((await (await h.weekly()).json()).status, "needs_review");
  assert.equal(h.calls.filter(call => call.path === "/emailCampaigns").length, 1);
  assert.equal(h.calls.filter(call => call.path.endsWith("/sendNow")).length, 0);
});

test("uncertain delivery reconciles the same ID and never resends a draft automatically", async () => {
  const h = harness({ audience: 1, providerFailure: ({ path }) => path.endsWith("/sendNow") ? "timeout" : undefined });
  assert.equal((await h.weekly()).status, 503);
  h.fail(undefined);
  assert.equal((await (await h.weekly()).json()).status, "needs_review");
  h.campaigns.get(1).status = "sent";
  assert.equal((await (await h.weekly()).json()).status, "sent");
  assert.equal(h.calls.filter(call => call.path === "/emailCampaigns" && call.method === "POST").length, 1);
  assert.equal(h.calls.filter(call => call.path.endsWith("/sendNow")).length, 1);
});

test("an unresolved previous campaign blocks the next week rather than risking duplicate delivery", async () => {
  const h = harness({ audience: 1, providerFailure: ({ path }) => path.endsWith("/sendNow") ? "timeout" : undefined });
  await h.weekly();
  h.advance(7 * 86400_000);
  h.fail(undefined);
  assert.equal((await (await h.weekly()).json()).status, "needs_review");
  assert.equal(h.calls.filter(call => call.path === "/emailCampaigns" && call.method === "POST").length, 1);
});

test("configuration rejects invented Vercel senders and nonnumeric list IDs", async () => {
  for (const env of [
    { NEWSLETTER_FROM: "newsletter@hackathon-milano.vercel.app" },
    { NEWSLETTER_FROM: "newsletter@vercel.app" },
    { NEWSLETTER_FROM: "Hackathon Milano <hello@example.test>" },
    { BREVO_LIST_ID: "not-a-list" }, { BREVO_LIST_ID: "0" },
  ]) {
    const h = harness({ env });
    assert.equal((await h.signup()).status, 503);
    assert.equal(h.calls.length, 0);
  }
});

test("free-only delivery stops on paid, unknown, exhausted or disabled account state", async () => {
  for (const account of [
    {},
    { plan: [{ type: "subscription", creditsType: "sendLimit", credits: 300 }], relay: { enabled: true } },
    { plan: [{ type: "free", creditsType: "sendLimit", credits: "300" }], relay: { enabled: true } },
    { plan: [{ type: "free", creditsType: "sendLimit", credits: 0 }], relay: { enabled: true } },
    { plan: [{ type: "free", creditsType: "sendLimit", credits: 300 }], relay: { enabled: false } },
    { plan: [{ type: "free", creditsType: "sendLimit", credits: 300 }, { type: "payAsYouGo", credits: 1000 }], relay: { enabled: true } },
  ]) {
    const h = harness({ account, audience: 1 });
    assert.equal((await h.signup()).status, 503);
    assert.equal((await h.weekly()).status, 503);
    assert.ok(h.calls.every(call => call.method === "GET"));
  }
});

test("last subscriber slot is reserved atomically despite concurrent confirms and stale list totals", async () => {
  const h = harness({ audience: 249 });
  await h.signup("first@example.test");
  const first = h.token();
  await h.signup("second@example.test");
  const second = h.token();
  const responses = await Promise.all([h.confirm(first), h.confirm(second)]);
  assert.deepEqual(responses.map(response => response.status).sort(), [200, 503]);
  assert.equal(h.get(`${PREFIX}subscriber-slots`), 250);
  assert.equal(h.calls.filter(call => call.path === "/contacts" && call.method === "POST").length, 1);
  assert.equal(h.calls.find(call => call.path === "/contacts" && call.method === "POST").payload.updateEnabled, false);
});

test("an uncertain contact create reuses its slot after provider reconciliation", async () => {
  const h = harness({ audience: 249 });
  await h.signup();
  h.fail(({ path, payload }) => {
    if (path !== "/contacts") return;
    h.contacts.set(payload.email, { email: payload.email, emailBlacklisted: false, listIds: [12] });
    return "timeout";
  });
  assert.equal((await h.confirm()).status, 503);
  h.fail(undefined);
  assert.equal((await h.confirm()).status, 200);
  assert.equal(h.get(`${PREFIX}subscriber-slots`), 250);
  assert.equal(h.calls.filter(call => call.path === "/contacts" && call.method === "POST").length, 1);
});

test("existing list-specific opt-outs and unrelated contacts are never overwritten", async () => {
  for (const record of [
    { emailBlacklisted: false, listIds: [12], listUnsubscribed: [12] },
    { emailBlacklisted: false, listIds: [99] },
    { listIds: [12] },
  ]) {
    const h = harness({ contacts: [["reader@example.test", record]] });
    await h.signup();
    assert.equal((await h.confirm()).status, 409);
    assert.ok(!h.calls.some(call => call.path.startsWith("/contacts") && call.method !== "GET"));
  }
});

test("the global confirmation quota covers every rolling 24-hour interval under concurrency", async () => {
  const h = harness();
  const requests = Array.from({ length: 41 }, (_, i) => h.signup(`reader-${i}@example.test`, { headers: { "x-forwarded-for": `192.0.2.${i + 1}` } }));
  const results = await Promise.all(requests);
  assert.equal(results.filter(response => response.status === 202).length, 40);
  assert.equal(results.filter(response => response.status === 429).length, 1);
  assert.equal(h.calls.filter(call => call.path === "/smtp/email").length, 40);
  h.advance(86401_000);
  assert.equal((await h.signup("next-day@example.test")).status, 202);
});

test("campaign creation is paused with no subscribers, an oversized list or insufficient credits", async () => {
  const empty = harness();
  assert.equal((await (await empty.weekly()).json()).status, "no_subscribers");
  assert.ok(!empty.calls.some(call => call.method !== "GET"));
  for (const options of [{ audience: 251 }, { audience: "1" }, { audience: 250, credits: 259 }]) {
    const h = harness(options);
    assert.equal((await h.weekly()).status, 503);
    assert.ok(!h.calls.some(call => call.method !== "GET"));
  }
  const atLimit = harness({ audience: 250, credits: 260 });
  assert.equal((await atLimit.weekly()).status, 200);
});

test("queued campaigns are checked without resending or prematurely recording successful delivery", async () => {
  const h = harness({ audience: 1, sentStatus: "queued" });
  assert.equal((await (await h.weekly()).json()).status, "processing");
  assert.equal((await (await h.weekly()).json()).status, "processing");
  assert.ok(![...h.store.keys()].some(key => key.includes(":sent-event:")));
  h.advance(7 * 86400_000);
  assert.equal((await (await h.weekly()).json()).status, "processing");
  h.campaigns.get(1).status = "sent";
  assert.equal((await (await h.weekly()).json()).status, "empty");
  assert.equal(h.calls.filter(call => call.path.endsWith("/sendNow")).length, 1);
  assert.ok([...h.store.keys()].some(key => key.includes(":sent-event:")));
});

test("a week-boundary retry cannot start two campaigns within a day", async () => {
  const h = harness({
    now: "2026-09-21T07:30:00Z", audience: 1,
    events: [baseEvent, { ...baseEvent, id: "previous-week", discovered_at: "2026-09-10T12:00:00Z" }],
  });
  assert.equal((await h.weekly()).status, 200);
  h.advance(3600_000);
  assert.equal((await h.weekly()).status, 503);
  assert.equal(h.calls.filter(call => call.path.endsWith("/sendNow")).length, 1);
  h.advance(86401_000);
  assert.equal((await h.weekly()).status, 200);
  assert.equal(h.calls.filter(call => call.path.endsWith("/sendNow")).length, 2);
});


test("a saved draft with a remote review state cannot proceed to sendNow", async () => {
  for (const status of ["suspended", "archive", "cancelled", "unknown"]) {
    const h = harness({ audience: 1 });
    h.set(`${PREFIX}week:2026-09-21`, JSON.stringify({ week: "2026-09-21", status: "draft", eventIds: ["event-one"], campaignId: 1 }));
    h.campaigns.set(1, { id: 1, status });
    assert.equal((await (await h.weekly()).json()).status, "needs_review");
    assert.ok(!h.calls.some(call => call.method !== "GET"));
  }
});
