export type ThemePreference = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "hackathon-mi:theme";

export function parseThemePreference(value: unknown): ThemePreference {
  return value === "light" || value === "dark" ? value : "system";
}

// Runs in the document head, before content paints. Keep the fallback identical
// to the control: a missing, unavailable or invalid preference follows the OS.
export const THEME_BOOTSTRAP = `(() => {
  let preference = "system";
  try {
    const stored = localStorage.getItem("${THEME_STORAGE_KEY}");
    if (stored === "light" || stored === "dark") preference = stored;
  } catch {}
  const theme = preference === "system"
    ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
    : preference;
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.dataset.themePreference = preference;
  root.style.colorScheme = theme;
  const chrome = document.querySelector('meta[name="theme-color"]');
  if (chrome) chrome.setAttribute("content", theme === "dark" ? "#111914" : "#f5f4ee");
})();`;
