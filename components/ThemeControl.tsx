"use client";

import { useEffect, useState } from "react";
import { parseThemePreference, THEME_STORAGE_KEY, type ThemePreference } from "@/lib/theme";
import "./theme-control.css";

const labels = { system: "Sistema", light: "Chiaro", dark: "Scuro" } as const;

function applyTheme(preference: ThemePreference, systemDark: boolean) {
  const theme = preference === "system" ? (systemDark ? "dark" : "light") : preference;
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.style.colorScheme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#111914" : "#f5f4ee");
}

export default function ThemeControl() {
  const [preference, setPreference] = useState<ThemePreference>("system");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    // The early bootstrap also handles unavailable localStorage. Its preference
    // is authoritative on hydration, so the first client render matches the SSR.
    let current = parseThemePreference(document.documentElement.dataset.themePreference);
    setPreference(current);
    applyTheme(current, media.matches);
    setReady(true);

    const handleSystemChange = () => {
      current = parseThemePreference(document.documentElement.dataset.themePreference);
      if (current === "system") applyTheme(current, media.matches);
    };
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY && event.key !== null) return;
      current = parseThemePreference(event.newValue);
      setPreference(current);
      applyTheme(current, media.matches);
    };
    media.addEventListener("change", handleSystemChange);
    window.addEventListener("storage", handleStorage);
    return () => {
      media.removeEventListener("change", handleSystemChange);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  function changeTheme(next: ThemePreference) {
    setPreference(next);
    applyTheme(next, window.matchMedia("(prefers-color-scheme: dark)").matches);
    try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch { /* The choice still applies to this page. */ }
  }

  return (
    <label className="theme-control" title={`Tema: ${labels[preference]}`}>
      <span className="sr-only">Tema</span>
      <svg className="theme-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        {preference === "system" ? <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8m-4-4v4" /></> : preference === "light" ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></> : <path d="M20.5 14a8.6 8.6 0 0 1-10.6-10.6A8.7 8.7 0 1 0 20.5 14Z" />}
      </svg>
      <select value={preference} disabled={!ready} onChange={(event) => changeTheme(parseThemePreference(event.target.value))} aria-label="Tema">
        <option value="system">Sistema</option>
        <option value="light">Chiaro</option>
        <option value="dark">Scuro</option>
      </select>
      <svg className="theme-control-chevron" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true"><path d="m3 4.5 3 3 3-3" /></svg>
    </label>
  );
}
