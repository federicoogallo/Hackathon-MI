import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(new URL("../lib/analytics.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { analyticsPageUrl } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const origin = "https://hackathon-milano.vercel.app";

test("analytics excludes email confirmation, unknown paths and other hosts", () => {
  for (const path of ["/newsletter/confirm#token=secret", "/api/newsletter/subscribe", "/person@example.org", "/unknown"]) {
    assert.equal(analyticsPageUrl(`${origin}${path}`, origin), null);
  }
  assert.equal(analyticsPageUrl("https://preview.vercel.app/", origin), null);
  assert.equal(analyticsPageUrl("invalid", origin), null);
});

test("analytics retains only public paths without search terms or fragments", () => {
  for (const path of ["/", "/privacy", "/review"]) {
    assert.equal(analyticsPageUrl(`${origin}${path}?q=person%40example.org&saved=1#token=secret`, origin), `${origin}${path}`);
  }
});
