/**
 * Dates de séance et fraîcheur des données (spec F09 — R6, R11, Définitions). Module pur :
 * l'instant présent est toujours passé en paramètre.
 *
 * Une date de séance (`CivilDate`) est une chaîne `YYYY-MM-DD` du contrat. Elle n'est jamais
 * convertie en instant : `new Date("2026-11-23")` serait interprété en UTC et reculerait d'un
 * jour dans les fuseaux américains. Les calculs passent par un numéro de jour entier.
 */

/** Date civile `YYYY-MM-DD` (date de séance du contrat). */
export type CivilDate = string;

const MS_PER_DAY = 86_400_000;
const CIVIL_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Numéro de jour depuis le 1970-01-01 (jour 0, un jeudi), sans aucun fuseau. */
export function dayNumber(d: CivilDate): number {
  const match = CIVIL_DATE.exec(d);
  if (match === null) throw new RangeError(`Date civile invalide : "${d}"`);
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const n = Date.UTC(year, month - 1, day) / MS_PER_DAY;
  if (fromDayNumber(n) !== d) throw new RangeError(`Date civile inexistante : "${d}"`);
  return n;
}

/** Date civile du jour numéro `n`. */
export function fromDayNumber(n: number): CivilDate {
  return new Date(n * MS_PER_DAY).toISOString().slice(0, 10);
}

/** 0 = dimanche … 6 = samedi. */
function weekday(n: number): number {
  return (((n + 4) % 7) + 7) % 7;
}

function isWeekday(n: number): boolean {
  const w = weekday(n);
  return w !== 0 && w !== 6;
}

/** Nombre de jours du lundi au vendredi de numéro strictement inférieur à `n` (depuis un lundi de référence). */
function weekdaysBefore(n: number): number {
  const k = n - 4; // jour 4 = lundi 1970-01-05
  const weeks = Math.floor(k / 7);
  const rest = k - weeks * 7;
  return weeks * 5 + Math.min(rest, 5);
}

const NEW_YORK = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** Date civile du jour à New York (`America/New_York`) pour l'instant `now`. */
export function todayInNewYork(now: Date): CivilDate {
  const parts = Object.fromEntries(NEW_YORK.formatToParts(now).map((p) => [p.type, p.value]));
  return `${parts.year ?? ""}-${parts.month ?? ""}-${parts.day ?? ""}`;
}

/** `S'` : dernier jour du lundi au vendredi strictement antérieur à `today`. */
export function lastAssumedSession(today: CivilDate): CivilDate {
  let n = dayNumber(today) - 1;
  while (!isWeekday(n)) n--;
  return fromDayNumber(n);
}

/**
 * Retard de `d` en séances : jours du lundi au vendredi dans `]d, S']` (0 si `d >= S'`).
 * Approximation du calendrier NYSE (décision Q2) : un jour férié compte comme une séance.
 */
export function sessionsBehind(d: CivilDate, today: CivilDate): number {
  const from = dayNumber(d) + 1;
  const to = dayNumber(lastAssumedSession(today)) + 1;
  return Math.max(0, weekdaysBefore(to) - weekdaysBefore(from));
}

/** Périodes du sélecteur de la page Ticker (R16). */
export type Period = "1M" | "6M" | "1A" | "5A" | "Max";

export const PERIODS: readonly Period[] = ["1M", "6M", "1A", "5A", "Max"];

const PERIOD_MONTHS: Record<Exclude<Period, "Max">, number> = { "1M": 1, "6M": 6, "1A": 12, "5A": 60 };

function pad(n: number, width: number): string {
  return String(n).padStart(width, "0");
}

/**
 * Borne inférieure d'une période : `last` − N mois calendaires, jour borné à la fin du mois
 * d'arrivée (31 mars − 1 mois = 28 ou 29 février). `null` pour Max (aucune borne).
 */
export function periodStart(last: CivilDate, period: Period): CivilDate | null {
  if (period === "Max") return null;
  dayNumber(last); // valide la date
  const year = Number(last.slice(0, 4));
  const month = Number(last.slice(5, 7));
  const day = Number(last.slice(8, 10));
  const index = year * 12 + (month - 1) - PERIOD_MONTHS[period];
  const y = Math.floor(index / 12);
  const m = index - y * 12 + 1;
  const monthLength = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return `${pad(y, 4)}-${pad(m, 2)}-${pad(Math.min(day, monthLength), 2)}`;
}

/** Seuil de péremption, identique à F02 : périmé si le retard dépasse 3 séances. */
export const STALE_AFTER = 3;

export type Freshness =
  | { kind: "none" }
  | { kind: "fresh"; behind: number }
  | { kind: "stale"; behind: number };

/** État de fraîcheur de `data_as_of` à la date `today` (R6). */
export function freshness(dataAsOf: CivilDate | null, today: CivilDate): Freshness {
  if (dataAsOf === null) return { kind: "none" };
  const behind = sessionsBehind(dataAsOf, today);
  return behind > STALE_AFTER ? { kind: "stale", behind } : { kind: "fresh", behind };
}
