"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useSyncExternalStore,
  type ReactNode,
} from "react";

export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "methatrace-theme";

const listeners = new Set<() => void>();

function emitThemeChange() {
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Reads the theme that the pre-hydration script applied to <html>. Using the
 * DOM as the source of truth keeps the CSS, React state and the maps in sync
 * without a second flash after hydration.
 */
export function getAppliedTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function getServerTheme(): Theme {
  return "dark";
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
}

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(
    subscribe,
    getAppliedTheme,
    getServerTheme
  );

  const setTheme = useCallback((next: Theme) => {
    applyTheme(next);

    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Storage can be unavailable (private mode, blocked cookies). The theme
      // still applies for the current page session.
    }

    emitThemeChange();
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(getAppliedTheme() === "light" ? "dark" : "light");
  }, [setTheme]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");

    const handleSystemChange = (event: MediaQueryListEvent) => {
      let stored: string | null = null;

      try {
        stored = window.localStorage.getItem(THEME_STORAGE_KEY);
      } catch {
        // Ignore unavailable storage.
      }

      // An explicit user choice always wins over the system preference.
      if (stored === "light" || stored === "dark") return;

      applyTheme(event.matches ? "light" : "dark");
      emitThemeChange();
    };

    media.addEventListener("change", handleSystemChange);
    return () => media.removeEventListener("change", handleSystemChange);
  }, []);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) return;
      if (event.newValue !== "light" && event.newValue !== "dark") return;

      applyTheme(event.newValue);
      emitThemeChange();
    };

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);

  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }

  return context;
}
