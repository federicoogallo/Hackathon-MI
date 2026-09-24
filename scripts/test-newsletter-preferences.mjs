import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

function compile(relativePath, jsx = false) {
  return ts.transpileModule(fs.readFileSync(new URL(relativePath, import.meta.url), "utf8"), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, ...(jsx ? { jsx: ts.JsxEmit.ReactJSX } : {}) },
  }).outputText;
}
const preferencesCode = compile("../lib/newsletter-preferences.ts");
const confirmationCode = compile("../components/NewsletterConfirmation.tsx", true);

function preferencesHarness({ stored = [], blockedRead = false, blockedWrite = false, blockedAccess = false, server = false } = {}) {
  const values = new Map(stored);
  const writes = [];
  const events = [];
  const storage = {
    getItem(key) { if (blockedRead) throw new Error("Storage blocked"); return values.get(key) ?? null; },
    setItem(key, value) { if (blockedWrite) throw new Error("Storage full"); writes.push({ key, value }); values.set(key, value); },
  };
  const window = {
    get localStorage() { if (blockedAccess) throw new Error("Storage access denied"); return storage; },
    dispatchEvent(event) { events.push(event); return true; },
  };
  const module = { exports: {} };
  vm.runInNewContext(preferencesCode, { module, exports: module.exports, Event, ...(server ? {} : { window }) });
  return { api: module.exports, values, writes, events, storage };
}

function plain(value) { return JSON.parse(JSON.stringify(value)); }

test("default and unknown modes behave as first-visit, independently from old preview flags", () => {
  const { api } = preferencesHarness({ stored: [["hackathon-mi:newsletter-seen", "1"]] });
  const preferences = api.readNewsletterPreferences();
  assert.deepEqual(plain(preferences), { seen: false, confirmed: false });
  for (const mode of [undefined, "", "first-visit", "invalid", "ALWAYS"]) {
    assert.equal(api.shouldAutoPrompt(true, mode, preferences), true);
    assert.equal(api.shouldAutoPrompt(true, mode, { seen: true, confirmed: false }), false);
  }
});

test("availability and confirmed status always take precedence over all prompt modes", () => {
  const { api } = preferencesHarness();
  for (const mode of [undefined, "first-visit", "always", "off", "unknown"]) {
    for (const seen of [true, false]) {
      assert.equal(api.shouldAutoPrompt(false, mode, { seen, confirmed: false }), false);
      assert.equal(api.shouldAutoPrompt(true, mode, { seen, confirmed: true }), false);
    }
  }
  assert.equal(api.shouldAutoPrompt(true, "off", { seen: false, confirmed: false }), false);
  assert.equal(api.shouldAutoPrompt(true, "always", { seen: true, confirmed: false }), true);
});

test("seeing an invitation stores only its flag and not a confirmed subscription", () => {
  const h = preferencesHarness();
  h.api.markNewsletterInviteSeen();
  assert.deepEqual(h.writes, [{ key: h.api.NEWSLETTER_SEEN_KEY, value: "1" }]);
  assert.deepEqual(plain(h.api.readNewsletterPreferences()), { seen: true, confirmed: false });
  assert.equal(h.events.length, 1);
  assert.equal(h.events[0].type, h.api.NEWSLETTER_STORAGE_EVENT);
  assert.equal(h.events[0].detail, undefined);
});

test("a confirmed marker persists both flags and notifies the same tab without personal data", () => {
  const h = preferencesHarness();
  h.api.markNewsletterConfirmed();
  assert.deepEqual(plain(h.api.readNewsletterPreferences()), { seen: true, confirmed: true });
  assert.deepEqual(h.writes, [
    { key: h.api.NEWSLETTER_SEEN_KEY, value: "1" },
    { key: h.api.NEWSLETTER_CONFIRMED_KEY, value: "1" },
  ]);
  assert.equal(h.events.length, 1);
  assert.equal(h.events[0].type, h.api.NEWSLETTER_STORAGE_EVENT);
  const freshVisit = preferencesHarness({ stored: [...h.values] });
  assert.deepEqual(plain(freshVisit.api.readNewsletterPreferences()), { seen: true, confirmed: true });
});

test("storage updates from another tab are read fresh, while only exact flags are accepted", () => {
  const h = preferencesHarness();
  assert.equal(h.api.readNewsletterPreferences().confirmed, false);
  h.values.set(h.api.NEWSLETTER_CONFIRMED_KEY, "1");
  assert.equal(h.api.readNewsletterPreferences().confirmed, true);
  for (const value of ["true", "yes", "0", "", "reader@example.invalid"]) {
    const other = preferencesHarness({ stored: [[h.api.NEWSLETTER_CONFIRMED_KEY, value], [h.api.NEWSLETTER_SEEN_KEY, value]] });
    assert.deepEqual(plain(other.api.readNewsletterPreferences()), { seen: false, confirmed: false });
  }
});

test("blocked storage, quota failures and server rendering cannot break the flow", () => {
  for (const options of [{ blockedAccess: true }, { blockedRead: true, blockedWrite: true }, { blockedWrite: true }, { server: true }]) {
    const h = preferencesHarness(options);
    assert.deepEqual(plain(h.api.readNewsletterPreferences()), { seen: false, confirmed: false });
    assert.doesNotThrow(() => h.api.markNewsletterInviteSeen());
    assert.equal(h.api.shouldAutoPrompt(true, undefined, h.api.readNewsletterPreferences()), false);
    assert.doesNotThrow(() => h.api.markNewsletterConfirmed());
    assert.equal(h.api.shouldAutoPrompt(true, "always", h.api.readNewsletterPreferences()), false);
  }
});

test("explicit storage can be injected without accessing a blocked browser getter", () => {
  const h = preferencesHarness({ blockedAccess: true });
  h.api.markNewsletterConfirmed(h.storage);
  assert.deepEqual(plain(h.api.readNewsletterPreferences(h.storage)), { seen: true, confirmed: true });
  assert.equal(h.writes.length, 2);
});

function confirmationHarness({ status = 200, brokenJson = false, offline = false } = {}) {
  const hooks = [];
  let cursor = 0;
  let markerCalls = 0;
  const requests = [];
  const react = {
    useRef(value) { const index = cursor++; if (!(index in hooks)) hooks[index] = { current: value }; return hooks[index]; },
    useState(value) { const index = cursor++; if (!(index in hooks)) hooks[index] = value; return [hooks[index], value => { hooks[index] = value; }]; },
    useEffect(effect) { effect(); },
  };
  const jsx = (type, props) => ({ type, props });
  const module = { exports: {} };
  const require = name => {
    if (name === "react") return react;
    if (name === "react/jsx-runtime") return { jsx, jsxs: jsx };
    if (name === "next/link") return { default: "link" };
    if (name === "@/lib/newsletter-preferences") return { markNewsletterConfirmed() { markerCalls++; } };
    throw new Error(`Unexpected import: ${name}`);
  };
  const window = { location: { hash: `#token=${"a".repeat(64)}`, pathname: "/newsletter/confirm" }, history: { replaceState() {} } };
  const fetch = async (url, init) => {
    requests.push({ url, ...init });
    if (offline) throw new Error("Offline");
    if (brokenJson) return new Response("not JSON", { status });
    return Response.json({ message: status === 200 ? "Confermato" : "Non confermato" }, { status });
  };
  vm.runInNewContext(confirmationCode, { module, exports: module.exports, require, window, URLSearchParams, fetch });
  function render() { cursor = 0; return module.exports.default(); }
  const findButton = tree => {
    if (!tree || typeof tree !== "object") return;
    if (tree.type === "button") return tree;
    for (const child of [tree.props?.children].flat(Infinity)) { const found = findButton(child); if (found) return found; }
  };
  render();
  const button = findButton(render());
  return { confirm: () => button.props.onClick(), requests, markerCalls: () => markerCalls };
}

test("the confirmation page marks the browser only after a successful confirmation POST", async () => {
  const success = confirmationHarness();
  assert.equal(success.markerCalls(), 0);
  await success.confirm();
  assert.equal(success.markerCalls(), 1);
  assert.equal(success.requests[0].url, "/api/newsletter/confirm");
  assert.equal(success.requests[0].method, "POST");
  assert.equal(JSON.parse(success.requests[0].body).token, "a".repeat(64));
  for (const options of [{ status: 400 }, { status: 409 }, { status: 503 }, { brokenJson: true }, { offline: true }]) {
    const failed = confirmationHarness(options);
    await failed.confirm();
    assert.equal(failed.markerCalls(), 0);
  }
});
