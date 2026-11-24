/* Généré par `npm run gen:types` depuis schemas/export_ticker.schema.json — ne pas modifier. */

/**
 * `tickers/{SYMBOL}.json` (R6, R9).
 */
export interface TickerFile {
  schema_version: 1;
  symbol: string;
  series: TickerSeries;
  markers: ExportMarker[];
}
/**
 * Colonnes de la fiche ticker (R6), toutes de même longueur ; `null` pendant le warm-up (R8).
 *
 * OHLC ajustés des splits (tels que stockés, §2) ; indicateurs calculés sur `close`.
 */
export interface TickerSeries {
  date: string[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  volume: number[];
  sma20: (number | null)[];
  sma50: (number | null)[];
  sma200: (number | null)[];
  bb_upper: (number | null)[];
  bb_lower: (number | null)[];
  rsi14: (number | null)[];
}
/**
 * Signal BUY/SELL affiché sur le graphique d'un ticker (R9) ; les HOLD ne sont pas exportés.
 */
export interface ExportMarker {
  date: string;
  strategy_id: string;
  action: "BUY" | "SELL";
  confidence: number;
}
