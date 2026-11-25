/**
 * Formats d'affichage `fr-FR` (spec F09 — R11). Module pur.
 *
 * Les séparateurs sont fixés ici plutôt que laissés à `Intl`, dont la sortie varie selon la
 * version d'ICU (navigateur ou Node) et qui écrirait « $US » pour le dollar :
 * - milliers : espace fine insécable (U+202F) ;
 * - avant `$` et `%` : espace insécable (U+00A0) ;
 * - signe moins : U+2212.
 * Une valeur `null` ou non finie s'affiche « — ».
 */

/** Valeur indisponible. */
export const EMPTY = "—";

const THIN = "\u202f";
const NBSP = "\u00a0";
const MINUS = "\u2212";

const formatters = new Map<number, Intl.NumberFormat>();

/** `Intl` en `fr-FR` à `decimals` décimales exactement, mis en cache. */
function formatter(decimals: number): Intl.NumberFormat {
  let f = formatters.get(decimals);
  if (f === undefined) {
    f = new Intl.NumberFormat("fr-FR", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
      useGrouping: true,
    });
    formatters.set(decimals, f);
  }
  return f;
}

/**
 * Nombre formaté à `decimals` décimales, séparateurs normalisés. Le signe est géré ici, pas
 * par `Intl` : aucun signe pour une valeur qui s'arrondit à zéro (pas de « −0,00 »).
 */
function formatNumber(x: number, decimals: number, signed: boolean): string {
  const digits = formatter(decimals)
    .format(Math.abs(x))
    .replace(/\s/g, THIN); // \s couvre U+00A0 et U+202F
  if (!/[1-9]/.test(digits)) return digits;
  if (x < 0) return `${MINUS}${digits}`;
  return signed ? `+${digits}` : digits;
}

function isNumber(x: number | null): x is number {
  return x !== null && Number.isFinite(x);
}

/** Prix : 2 décimales à partir de 1 $, 4 en dessous (cours anciens ajustés des splits). */
export function formatPrice(x: number | null): string {
  if (!isNumber(x)) return EMPTY;
  return `${formatNumber(x, Math.abs(x) >= 1 ? 2 : 4, false)}${NBSP}$`;
}

/** Montant (equity, cash) : 2 décimales, séparateur de milliers, devise. */
export function formatAmount(x: number | null): string {
  if (!isNumber(x)) return EMPTY;
  return `${formatNumber(x, 2, false)}${NBSP}$`;
}

/** Ratio (rendement, poids, métrique) en pourcentage à 2 décimales ; `signed` pour une variation. */
export function formatPercent(x: number | null, opts: { signed?: boolean } = {}): string {
  if (!isNumber(x)) return EMPTY;
  return `${formatNumber(x * 100, 2, opts.signed ?? false)}${NBSP}%`;
}

/** Ratio sans unité (ex. Sharpe) à 2 décimales. */
export function formatDecimal(x: number | null): string {
  if (!isNumber(x)) return EMPTY;
  return formatNumber(x, 2, false);
}

/** Confiance (dans [0, 1]) en pourcentage entier. */
export function formatConfidence(x: number | null): string {
  if (!isNumber(x)) return EMPTY;
  return `${formatNumber(x * 100, 0, false)}${NBSP}%`;
}

const SESSION_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Date de séance `YYYY-MM-DD` → `JJ/MM/AAAA`, par simple découpage (jamais via `Date`). */
export function formatDate(d: string | null): string {
  const match = d === null ? null : SESSION_DATE.exec(d);
  if (match === null) return EMPTY;
  const [, year, month, day] = match;
  return `${day ?? ""}/${month ?? ""}/${year ?? ""}`;
}

/** Direction d'une variation. */
export type ChangeDirection = "up" | "down" | "flat" | "none";

/** Variation prête à afficher : la flèche et le signe doublent la couleur (R8). */
export interface ChangeParts {
  direction: ChangeDirection;
  arrow: "▲" | "▼" | "";
  text: string;
}

/** Décompose une variation (ratio) en direction, flèche et texte signé. */
export function changeParts(x: number | null): ChangeParts {
  if (!isNumber(x)) return { direction: "none", arrow: "", text: EMPTY };
  const text = formatPercent(x, { signed: true });
  if (text.startsWith("+")) return { direction: "up", arrow: "▲", text };
  if (text.startsWith(MINUS)) return { direction: "down", arrow: "▼", text };
  return { direction: "flat", arrow: "", text };
}
