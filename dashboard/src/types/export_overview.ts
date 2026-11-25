/* Généré par `npm run gen:types` depuis schemas/export_overview.schema.json — ne pas modifier. */

/**
 * `overview.json` (R10, R16).
 */
export interface OverviewFile {
  schema_version: 1;
  data_as_of: string | null;
  tickers: OverviewTicker[];
  leaderboard: LeaderboardRow[];
  latest_signals: ExportSignal[];
  kpis: Kpis;
}
/**
 * Résumé d'un symbole pour la page d'accueil (R10).
 */
export interface OverviewTicker {
  symbol: string;
  last_close: number;
  change_1d: number | null;
  /**
   * @maxItems 60
   */
  spark: number[];
}
/**
 * Ligne du classement des stratégies (M3, R16) ; baselines toujours présentes (P3).
 */
export interface LeaderboardRow {
  strategy_id: string;
  kind: "baseline" | "model";
  equity: number;
  return_30d: number | null;
  sharpe_oos: number | null;
  random_percentile: number | null;
}
/**
 * Signal du §4 enrichi du modèle qui l'a produit et de sa performance historique (M3, P8).
 */
export interface ExportSignal {
  strategy_id: string;
  symbol: string;
  action: "BUY" | "HOLD" | "SELL";
  confidence: number;
  target_weight: number;
  horizon_days: number;
  explanation?:
    | []
    | [FeatureContribution]
    | [FeatureContribution, FeatureContribution]
    | [FeatureContribution, FeatureContribution, FeatureContribution]
    | [FeatureContribution, FeatureContribution, FeatureContribution, FeatureContribution]
    | [FeatureContribution, FeatureContribution, FeatureContribution, FeatureContribution, FeatureContribution]
    | null;
  model_id: string | null;
  sharpe_oos: number | null;
}
/**
 * Contribution d'une feature à la prédiction (SHAP / gain).
 */
export interface FeatureContribution {
  feature: string;
  contribution: number;
}
/**
 * Indicateurs clés de l'accueil (M3, R16).
 */
export interface Kpis {
  best_strategy_30d: string | null;
}
