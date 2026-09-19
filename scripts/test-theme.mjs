// Exercise the exact inline bootstrap that runs before hydration, without a
// browser dependency or access to the user's actual appearance preference.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../lib/theme.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;
const module = { exports: {} };
vm.runInNewContext(compiled, { module, exports: module.exports }, { filename: "lib/theme.ts" });
const { THEME_BOOTSTRAP, THEME_STORAGE_KEY, parseThemePreference } = module.exports;

function boot({ stored = null, systemDark = false, storageBlocked = false, hasMeta = true } = {}) {
  const root = { dataset: {}, style: {} };
  let chrome;
  vm.runInNewContext(THEME_BOOTSTRAP, {
    localStorage: {
      getItem(key) {
        assert.equal(key, THEME_STORAGE_KEY);
        if (storageBlocked) throw new Error("Storage unavailable");
        return stored;
      },
    },
    window: {
      matchMedia(query) {
        assert.equal(query, "(prefers-color-scheme: dark)");
        return { matches: systemDark };
      },
    },
    document: {
      documentElement: root,
      querySelector(selector) {
        assert.equal(selector, 'meta[name="theme-color"]');
        return hasMeta ? { setAttribute(name, value) { assert.equal(name, "content"); chrome = value; } } : null;
      },
    },
  }, { filename: "theme-bootstrap.js" });
  return { theme: root.dataset.theme, preference: root.dataset.themePreference, colorScheme: root.style.colorScheme, chrome };
}

test("initial appearance follows both OS schemes without a saved override", () => {
  assert.deepEqual(boot(), { theme: "light", preference: "system", colorScheme: "light", chrome: "#f5f4ee" });
  assert.deepEqual(boot({ systemDark: true }), { theme: "dark", preference: "system", colorScheme: "dark", chrome: "#111914" });
  assert.equal(boot({ stored: "system", systemDark: true }).theme, "dark");
});

test("explicit saved choices override the OS before hydration", () => {
  assert.deepEqual(boot({ stored: "dark", systemDark: false }), { theme: "dark", preference: "dark", colorScheme: "dark", chrome: "#111914" });
  assert.deepEqual(boot({ stored: "light", systemDark: true }), { theme: "light", preference: "light", colorScheme: "light", chrome: "#f5f4ee" });
});

test("unknown stored values fall back to system consistently with the control", () => {
  for (const value of ["", "invalid", "DARK", '"dark"', null, undefined]) {
    assert.equal(parseThemePreference(value), "system");
    assert.equal(boot({ stored: value, systemDark: true }).preference, "system");
    assert.equal(boot({ stored: value, systemDark: true }).theme, "dark");
  }
  assert.equal(parseThemePreference("light"), "light");
  assert.equal(parseThemePreference("dark"), "dark");
});

test("blocked storage and a missing browser chrome meta do not block theme resolution", () => {
  assert.deepEqual(boot({ storageBlocked: true, systemDark: true, hasMeta: false }), {
    theme: "dark", preference: "system", colorScheme: "dark", chrome: undefined,
  });
});
