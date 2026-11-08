"use client";

import { useTheme } from "./ThemeProvider";

function SunIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
    </svg>
  );
}

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === "light";
  const nextTheme = isLight ? "dark" : "light";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isLight}
      aria-label="Light mode"
      title={`Switch to ${nextTheme} mode`}
      onClick={toggleTheme}
      className={`inline-flex items-center gap-2.5 rounded-lg border border-border bg-surface-raised px-3 py-2 text-xs font-medium text-secondary transition hover:bg-surface-hover ${className}`}
    >
      <span aria-hidden="true" className="text-accent">
        {isLight ? <SunIcon /> : <MoonIcon />}
      </span>
      <span>{isLight ? "Light mode" : "Dark mode"}</span>
      <span
        aria-hidden="true"
        className={`relative ml-auto h-5 w-9 shrink-0 rounded-full border border-border transition-colors ${
          isLight ? "bg-accent/20" : "bg-surface-sunken"
        }`}
      >
        <span
          className={`absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all ${
            isLight ? "left-[1.25rem] bg-accent" : "left-0.5 bg-subtle"
          }`}
        />
      </span>
    </button>
  );
}
