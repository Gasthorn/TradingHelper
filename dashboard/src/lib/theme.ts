/**
 * Préférence de thème (spec F09 — R7, décision Q9). Module pur : la lecture de
 * `localStorage` et de `prefers-color-scheme` se fait côté appelant (`hooks/useTheme.ts`
 * et le script inline de `index.html`, qui utilise la même clé).
 */

export type ThemePreference = "light" | "dark" | "system";
export type Theme = "light" | "dark";

/** Clé `localStorage` de la préférence. */
export const THEME_KEY = "th-theme";

/** Ordre de la bascule à trois états ; `system` est le défaut. */
export const THEME_PREFERENCES: readonly ThemePreference[] = ["system", "light", "dark"];

/** Préférence stockée ; absente ou inconnue → `system`. */
export function parsePreference(raw: string | null): ThemePreference {
  return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
}

/** Thème effectif : la préférence explicite, sinon `prefers-color-scheme`. */
export function resolveTheme(pref: ThemePreference, prefersDark: boolean): Theme {
  if (pref === "system") return prefersDark ? "dark" : "light";
  return pref;
}

/** Préférence suivante dans la bascule (système → clair → sombre → système). */
export function nextPreference(pref: ThemePreference): ThemePreference {
  const i = THEME_PREFERENCES.indexOf(pref);
  return THEME_PREFERENCES[(i + 1) % THEME_PREFERENCES.length] ?? "system";
}
