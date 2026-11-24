/* Généré par `npm run gen:types` depuis schemas/export_health.schema.json — ne pas modifier. */

/**
 * `health.json` (R12).
 */
export interface HealthFile {
  schema_version: 1;
  last_session: string;
  tickers: HealthTicker[];
  /**
   * @maxItems 10
   */
  runs:
    | []
    | [HealthRun]
    | [HealthRun, HealthRun]
    | [HealthRun, HealthRun, HealthRun]
    | [HealthRun, HealthRun, HealthRun, HealthRun]
    | [HealthRun, HealthRun, HealthRun, HealthRun, HealthRun]
    | [HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun]
    | [HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun]
    | [HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun]
    | [HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun]
    | [HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun, HealthRun];
  /**
   * @maxItems 100
   */
  quality_warnings: ValidateWarning[];
  quality_warnings_truncated: number;
}
/**
 * Fraîcheur d'un symbole de l'univers ou du benchmark (R12).
 */
export interface HealthTicker {
  symbol: string;
  last_date: string | null;
  sessions_behind: number | null;
  stale: boolean;
}
/**
 * Résumé d'un rapport de run ; section absente → `null`. Sérialiser avec `by_alias=True`.
 */
export interface HealthRun {
  session_date: string;
  ingest: HealthIngest | null;
  validate: HealthValidate | null;
}
/**
 * Résumé de la dernière exécution `ingest` d'un rapport de run.
 */
export interface HealthIngest {
  exit_code: 0 | 1;
  ok: number;
  unchanged: number;
  failed: number;
  history_rewritten: string[];
}
/**
 * Résumé de la dernière exécution `validate` d'un rapport de run.
 */
export interface HealthValidate {
  exit_code: 0 | 1;
  violations: number;
  warnings: number;
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
