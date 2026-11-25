/**
 * En-tête du site (spec F09 — R1, R6) : titre-lien vers l'Overview, date des données et alerte
 * « Données périmées » calculée dans le navigateur à partir de la date du jour à New York
 * (et non depuis `health.json`, figé au dernier export). Bascule de thème à trois états (R7).
 */
import { freshness, todayInNewYork } from "../lib/dates";
import { formatDate } from "../lib/format";
import type { ThemePreference } from "../lib/theme";

const THEME_LABELS: Record<ThemePreference, string> = { system: "Système", light: "Clair", dark: "Sombre" };

function plural(n: number, word: string): string {
  return `${String(n)} ${word}${n > 1 ? "s" : ""}`;
}

/** `dataAsOf` : `undefined` tant que le manifest n'est pas chargé (ou en erreur). */
export function Header({
  dataAsOf,
  themePreference,
  onCycleTheme,
}: {
  dataAsOf: string | null | undefined;
  themePreference: ThemePreference;
  onCycleTheme: () => void;
}) {
  const state = dataAsOf === undefined ? null : freshness(dataAsOf, todayInNewYork(new Date()));
  return (
    <header class="site-header">
      <a class="site-title" href="#/">
        TradingHelper
      </a>
      {state !== null && state.kind !== "none" && dataAsOf != null && (
        <p class="data-date">
          Données au <time dateTime={dataAsOf}>{formatDate(dataAsOf)}</time>
          {state.kind === "stale" && (
            <span class="stale-badge" role="status">
              Données périmées ({plural(state.behind, "séance")})
            </span>
          )}
        </p>
      )}
      <button type="button" class="theme-toggle" onClick={onCycleTheme}>
        Thème : {THEME_LABELS[themePreference]}
      </button>
    </header>
  );
}
