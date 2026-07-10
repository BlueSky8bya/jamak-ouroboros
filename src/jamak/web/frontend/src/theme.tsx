import { useState } from "react";

export type Theme = "light" | "dark";
const KEY = "jamak-theme";

/** Apply saved theme, or fall back to the OS preference. Call once at startup
 *  (before render) so there's no flash of the wrong theme. */
export function initTheme(): Theme {
  const saved = localStorage.getItem(KEY) as Theme | null;
  const t: Theme =
    saved ??
    (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  document.documentElement.dataset.theme = t;
  return t;
}

export function setTheme(t: Theme): void {
  document.documentElement.dataset.theme = t;
  localStorage.setItem(KEY, t);
}

/** Sun/moon toggle. Dark mode is the single biggest fatigue win for long,
 *  low-light review sessions — keep it one glanceable control, no clutter. */
export function ThemeToggle() {
  const [t, setT] = useState<Theme>(
    () => (document.documentElement.dataset.theme as Theme) || "light",
  );
  const next = t === "dark" ? "light" : "dark";
  return (
    <button
      className="theme-toggle"
      title={t === "dark" ? "밝은 화면으로" : "어두운 화면으로 (눈 피로 줄이기)"}
      aria-label="화면 밝기 전환"
      onClick={() => {
        setTheme(next);
        setT(next);
      }}
    >
      {t === "dark" ? "☀" : "🌙"}
    </button>
  );
}
