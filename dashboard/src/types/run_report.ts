/* Généré par `npm run gen:types` depuis schemas/run_report.schema.json — ne pas modifier. */

/**
 * Rapport de run d'une séance. Chaque commande met à jour sa seule section ;
 * les sections des features suivantes (ex. `signal`) sont conservées telles quelles.
 *
 * Sérialiser avec `by_alias=True` (clé JSON `validate`) et `exclude_unset=True` (une section
 * absente du fichier n'y est pas ajoutée vide).
 */
export interface RunReport {
  schema_version: 1;
  session_date: string;
  ingest?: IngestRun[];
  validate?: ValidateRun[];
  [k: string]: unknown;
}
/**
 * Une exécution de `th ingest` (F01 R15).
 */
export interface IngestRun {
  started_at: string;
  finished_at: string;
  duration_s: number;
  args: IngestArgs;
  exit_code: 0 | 1;
  tickers: IngestTickerResult[];
  warnings: IngestWarning[];
}
/**
 * Arguments de `th ingest` journalisés (P4).
 */
export interface IngestArgs {
  symbols: string[] | null;
  full: boolean;
  start: string | null;
}
/**
 * Résultat de l'ingestion d'un symbole (F01 R15).
 */
export interface IngestTickerResult {
  symbol: string;
  status: "ok" | "unchanged" | "failed";
  mode: ("initial" | "incremental" | "full") | null;
  bars_added: number;
  bars_revised: number;
  history_rewritten: boolean;
  rewrite_reason: ("revision" | "backfill") | null;
  attempts: number;
  error: string | null;
}
/**
 * Barre écartée ou anomalie non bloquante (F01 R3, R6).
 */
export interface IngestWarning {
  symbol: string;
  date: string | null;
  rule:
    | "nan"
    | "non_session_date"
    | "after_last_session"
    | "non_positive_price"
    | "negative_volume"
    | "ohlc_inconsistent"
    | "duplicate_date"
    | "missing_overlap_bar";
}
/**
 * Une exécution de `th validate` (F02 R8).
 */
export interface ValidateRun {
  started_at: string;
  finished_at: string;
  duration_s: number;
  args: ValidateArgs;
  exit_code: 0 | 1;
  files_checked: number;
  violations: ValidateViolation[];
  warnings: ValidateWarning[];
}
/**
 * Arguments de `th validate` journalisés (P4).
 */
export interface ValidateArgs {
  symbols: string[] | null;
  all_history: boolean;
}
/**
 * Violation bloquante (F02 R1, R2). `symbol` est le nom du fichier sans `.json` : il peut
 * ne pas être un symbole valide (fichier orphelin quelconque).
 */
export interface ValidateViolation {
  symbol: string;
  date: string | null;
  rule:
    | "unreadable"
    | "schema"
    | "symbol_mismatch"
    | "empty_bars"
    | "dates_not_increasing"
    | "non_session_date"
    | "after_last_session"
    | "non_positive_price"
    | "negative_volume"
    | "ohlc_inconsistent"
    | "not_rounded";
  detail: string;
}
/**
 * Anomalie non bloquante (F02 R3), sur une barre (`start == end`) ou une plage de séances.
 *
 * `value` : variation simple pour `large_move`, nombre de séances pour `missing_session`
 * et `stale` ; absente sinon.
 */
export interface ValidateWarning {
  symbol: string;
  rule: "missing_session" | "large_move" | "zero_volume" | "stale" | "missing_file";
  start: string | null;
  end: string | null;
  value?: number | null;
}
