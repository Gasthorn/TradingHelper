/**
 * Thème de la page (spec F09 — R7) : préférence mémorisée dans `localStorage`, `system` suit
 * `prefers-color-scheme` en direct. Pose `data-theme` sur <html> (le script inline de
 * index.html le pose déjà avant le premier rendu).
 */
import { useEffect, useState } from "preact/hooks";

import { THEME_KEY, type Theme, type ThemePreference, nextPreference, parsePreference, resolveTheme } from "../lib/theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function readPreference(): ThemePreference {
  try {
    return parsePreference(window.localStorage.getItem(THEME_KEY));
  } catch {
    return "system"; // stockage indisponible (navigation privée stricte)
  }
}

function savePreference(pref: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_KEY, pref);
  } catch {
    // choix non mémorisé, mais appliqué
  }
}

export interface ThemeState {
  preference: ThemePreference;
  theme: Theme;
  cycle: () => void;
}

export function useTheme(): ThemeState {
  const [preference, setPreference] = useState<ThemePreference>(readPreference);
  const [prefersDark, setPrefersDark] = useState(() => window.matchMedia(DARK_QUERY).matches);

  useEffect(() => {
    const media = window.matchMedia(DARK_QUERY);
    const onChange = (event: MediaQueryListEvent) => {
      setPrefersDark(event.matches);
    };
    media.addEventListener("change", onChange);
    return () => {
      media.removeEventListener("change", onChange);
    };
  }, []);

  const theme = resolveTheme(preference, prefersDark);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  return {
    preference,
    theme,
    cycle: () => {
      const next = nextPreference(preference);
      setPreference(next);
      savePreference(next);
    },
  };
}
