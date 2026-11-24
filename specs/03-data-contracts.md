# Contrats de données

Source de vérité : modèles pydantic dans `src/tradinghelper/schemas.py`.
`th schemas` génère les JSON Schemas dans `schemas/` ; le dashboard en génère ses types TS
(`json-schema-to-typescript`). Toute modification de contrat incrémente `schema_version`, sauf l'ajout d'une section
ou d'un champ optionnel qui laisse valides les fichiers existants (ex. section `validate` du rapport de run, F02 R8).

## 1. Univers — `config/universe.yaml`
```yaml
currency: USD
benchmark: SPY
tickers:
  - { symbol: AAPL, name: Apple Inc., sector: Technology, start: 2010-01-01 }
  - { symbol: MSFT, name: Microsoft,  sector: Technology, start: 2010-01-01 }
  # ...
```

## 2. Prix bruts — `data/raw/prices/{SYMBOL}.json`
Une barre par ligne (P5). Format colonne-tableau compact.
```json
{
  "schema_version": 1,
  "symbol": "AAPL",
  "currency": "USD",
  "source": "yfinance",
  "columns": ["date", "open", "high", "low", "close", "adj_close", "volume"],
  "last_updated": "2026-11-23T22:41:05Z",
  "bars": [
    ["2026-11-20", 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000],
    ["2026-11-23", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000]
  ]
}
```
Règles : dates de séance NYSE strictement croissantes et uniques ; prix `> 0` arrondis à 4 décimales ;
`low <= min(open, close)` et `high >= max(open, close)` ; `volume` entier `>= 0`.

Sémantique des colonnes (F01 R5, yfinance `auto_adjust=False`) : `open`, `high`, `low`, `close` sont ajustés des
**splits uniquement** ; `adj_close` est ajusté des splits **et** des dividendes. Les features calculent le facteur
`adj_close / close`. Si yfinance réécrit l'historique ajusté, `th ingest` recalcule le fichier entier et le journalise
dans le rapport de run (`history_rewritten: true`, F01 R4).

`last_updated` (UTC ISO-8601) ne change que lorsque `bars` change.

**Sérialisation canonique** (idempotence et diffs, P5) : UTF-8, fins de ligne LF, saut de ligne final ; clés de premier
niveau dans l'ordre ci-dessus, indentation de 2 espaces ; **une barre par ligne**, sur une seule ligne, éléments séparés
par `", "` ; flottants écrits sous leur représentation la plus courte après arrondi à 4 décimales (`228.1`, pas `228.10`),
volume en entier. Deux sérialisations d'un même contenu sont identiques octet pour octet.

## 3. Portefeuille fictif — `data/portfolios/{strategy_id}.json`
```json
{
  "schema_version": 1,
  "strategy_id": "lgbm_dir5_v3",
  "inception": "2026-12-01",
  "initial_capital": 10000.0,
  "as_of": "2026-11-23",
  "cash": 1234.56,
  "positions": [{ "symbol": "AAPL", "qty": 10, "avg_cost": 220.1 }],
  "equity_curve": [["2026-12-01", 10000.0], ["2026-12-02", 10012.4]],
  "trades": [
    { "date": "2026-12-02", "symbol": "AAPL", "side": "BUY", "qty": 10, "price": 220.1, "fees": 1.0, "reason": "signal p=0.67" }
  ]
}
```
Invariant : `cash + Σ(qty × close) == equity_curve[-1].value` (à 1e-6 près).

## 4. Signaux — `data/signals/{YYYY-MM-DD}.json` (+ copie `latest.json`)
```json
{
  "schema_version": 1,
  "date": "2026-11-23",
  "generated_at": "2026-11-23T22:45:00Z",
  "signals": [
    {
      "strategy_id": "lgbm_dir5_v3",
      "symbol": "AAPL",
      "action": "BUY",
      "confidence": 0.67,
      "target_weight": 0.08,
      "horizon_days": 5,
      "explanation": [{ "feature": "rsi_14", "contribution": 0.12 }]
    }
  ]
}
```
`action ∈ {BUY, HOLD, SELL}` ; `confidence ∈ [0,1]` ; `explanation` optionnelle (top 5 contributions SHAP/gain).

## 5. Registre de modèles — `models/registry/registry.json` + `{model_id}/model_card.json`
```json
{
  "model_id": "lgbm_dir5_20261122_ab12cd",
  "family": "lgbm_dir5",
  "created_at": "2026-11-22T03:10:00Z",
  "git_sha": "ab12cd…",
  "data_hash": "sha256:…",
  "train_period": ["2012-01-01", "2024-12-31"],
  "oos_period": ["2025-01-01", "2026-11-21"],
  "seed": 42,
  "features": ["ret_1", "ret_5", "rsi_14", "…"],
  "hyperparams": { "num_leaves": 31, "learning_rate": 0.05 },
  "metrics_oos": { "cagr": 0.12, "sharpe": 1.1, "max_drawdown": -0.14, "hit_rate": 0.54, "auc": 0.56,
                   "random_percentile": 0.91, "excess_vs_buy_hold": 0.02 },
  "status": "champion"
}
```
`status ∈ {candidate, champion, retired}` — une seule `champion` par `family`.

## 6. Rapport de run — `data/runs/{YYYY-MM-DD}.json`
Nommé d'après la **dernière séance clôturée** `S` (et non la date UTC du run, le cron pouvant passer minuit).
Une section par étape ; chaque commande lit le fichier, met à jour **sa seule section** et le réécrit atomiquement.
Modèle pydantic `RunReport` dans `schemas.py`. Section `ingest` (F01 R15) = liste d'exécutions :
```json
{
  "schema_version": 1,
  "session_date": "2026-11-23",
  "ingest": [
    {
      "started_at": "2026-11-23T22:31:02Z",
      "finished_at": "2026-11-23T22:32:10Z",
      "duration_s": 68.4,
      "args": { "symbols": null, "full": false, "start": null },
      "exit_code": 0,
      "tickers": [
        { "symbol": "AAPL", "status": "ok", "mode": "incremental", "bars_added": 1, "bars_revised": 0,
          "history_rewritten": false, "rewrite_reason": null, "attempts": 1, "error": null },
        { "symbol": "MSFT", "status": "failed", "mode": "incremental", "bars_added": 0, "bars_revised": 0,
          "history_rewritten": false, "rewrite_reason": null, "attempts": 4, "error": "HTTP 429" }
      ],
      "warnings": [{ "symbol": "NVDA", "date": "2026-11-22", "rule": "non_session_date" }]
    }
  ]
}
```
`status ∈ {ok, unchanged, failed}` ; `mode ∈ {initial, incremental, full}` ; `rewrite_reason ∈ {revision, backfill, null}`.
Les sections des autres étapes sont définies par leurs features : `validate` (liste d'exécutions) par F02 R7–R8, etc.

## 7. Export dashboard — `dashboard/public/data/` (non commité)
| Fichier | Contenu | Taille cible |
|---|---|---|
| `manifest.json` | dates, liste tickers, stratégies, version | < 10 Ko |
| `overview.json` | leaderboard, derniers signaux, KPIs | < 100 Ko |
| `tickers/{SYMBOL}.json` | OHLCV + indicateurs (SMA20/50/200, RSI, Bollinger) + marqueurs de signaux | < 500 Ko |
| `portfolios/{strategy_id}.json` | courbe d'equity, positions, trades, drawdown | < 200 Ko |
| `models.json` | model cards, métriques OOS, distribution des random traders | < 200 Ko |
| `health.json` | fraîcheur des données, derniers runs | < 20 Ko |
