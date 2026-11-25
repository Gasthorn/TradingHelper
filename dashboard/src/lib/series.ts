/**
 * Séries de la fiche ticker (spec F09 — R15, R16). Module pur : les indicateurs exportés sont
 * affichés tels quels, sans recalcul ; seule la fenêtre visible change.
 */
import { type CivilDate, type Period, periodStart } from "./dates";

/** Fenêtre visible : indices inclusifs ; `to < from` pour une fenêtre vide. */
export interface BarWindow {
  from: number;
  to: number;
}

/** Point d'une série tracée. */
export interface LinePoint {
  time: CivilDate;
  value: number;
}

/**
 * Barres de la période : de la première séance `>=` `periodStart(dernière date)` à la dernière.
 * Les dates du contrat sont triées et au format `YYYY-MM-DD` : l'ordre lexical suffit.
 */
export function periodWindow(dates: readonly CivilDate[], period: Period): BarWindow {
  const to = dates.length - 1;
  const last = dates[to];
  if (last === undefined) return { from: 0, to: -1 };
  const start = periodStart(last, period);
  if (start === null) return { from: 0, to };
  let lo = 0;
  let hi = to;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((dates[mid] ?? "") < start) lo = mid + 1;
    else hi = mid;
  }
  return { from: lo, to };
}

/** Points de la fenêtre, valeurs `null` (warm-up) exclues : ni zéro ni interpolation (R15). */
export function linePoints(
  dates: readonly CivilDate[],
  values: readonly (number | null)[],
  w: BarWindow,
): LinePoint[] {
  const points: LinePoint[] = [];
  for (let i = Math.max(0, w.from); i <= w.to; i++) {
    const time = dates[i];
    const value = values[i];
    if (time !== undefined && value !== undefined && value !== null) points.push({ time, value });
  }
  return points;
}

/** Vrai si aucune valeur n'est disponible (ex. `sma200` sur moins de 200 barres). */
export function isAllNull(values: readonly (number | null)[]): boolean {
  return values.every((v) => v === null);
}
