/* Généré par `npm run gen:types` depuis schemas/signals.schema.json — ne pas modifier. */

/**
 * Signaux de toutes les stratégies actives pour une séance.
 */
export interface SignalsFile {
  schema_version: 1;
  date: string;
  generated_at: string;
  signals: Signal[];
}
/**
 * Signal d'une stratégie pour un symbole à une séance.
 */
export interface Signal {
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
}
/**
 * Contribution d'une feature à la prédiction (SHAP / gain).
 */
export interface FeatureContribution {
  feature: string;
  contribution: number;
}
