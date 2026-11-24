/* Généré par `npm run gen:types` depuis schemas/export_manifest.schema.json — ne pas modifier. */

/**
 * `manifest.json` (R11).
 */
export interface ManifestFile {
  schema_version: 1;
  generated_at: string;
  data_as_of: string | null;
  git_sha: string | null;
  currency: "USD";
  benchmark: string;
  tickers: ManifestTicker[];
  strategies: ManifestStrategy[];
  files: ManifestEntry[];
}
/**
 * Symbole exporté (R11) ; pour le benchmark hors univers, nom = symbole et secteur `null`.
 */
export interface ManifestTicker {
  symbol: string;
  name: string;
  sector: string | null;
  benchmark: boolean;
  first_date: string;
  last_date: string;
}
/**
 * Stratégie exportée (M3, R16) : modèle champion et performance, pour l'affichage P8.
 */
export interface ManifestStrategy {
  id: string;
  kind: "baseline" | "model";
  model_id: string | null;
  sharpe_oos: number | null;
}
/**
 * Fichier produit par l'export : empreinte pour le cache-busting du front (R11).
 */
export interface ManifestEntry {
  path: string;
  sha256: string;
  bytes: number;
}
