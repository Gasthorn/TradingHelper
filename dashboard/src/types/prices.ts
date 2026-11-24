/* Généré par `npm run gen:types` depuis schemas/prices.schema.json — ne pas modifier. */

/**
 * Prix bruts d'un symbole — `data/raw/prices/{SYMBOL}.json` (contrat §2).
 */
export interface PricesFile {
  schema_version: 1;
  symbol: string;
  currency: "USD";
  source: "yfinance";
  /**
   * @minItems 7
   * @maxItems 7
   */
  columns: [unknown, unknown, unknown, unknown, unknown, unknown, unknown];
  last_updated: string;
  bars: [unknown, unknown, unknown, unknown, unknown, unknown, unknown][];
}
