# Contrats de données

Source de vérité : modèles pydantic dans `src/tradinghelper/schemas.py`.
`th schemas` génère les JSON Schemas dans `schemas/` ; le dashboard en génère ses types TS
(`json-schema-to-typescript`). Toute modification de contrat incrémente `schema_version`.

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
    ["2026-11-20", 228.10, 231.45, 227.80, 230.95, 230.95, 51234000],
    ["2026-11-23", 231.00, 233.12, 229.60, 232.40, 232.40, 48765000]
  ]
}
```
Règles : dates strictement croissantes et uniques ; prix arrondis à 4 décimales ; `low <= open,close <= high` ;
`volume >= 0`. Les splits/dividendes sont gérés via `adj_close` ; si yfinance réécrit l'historique ajusté,
`th ingest` recalcule le fichier entier et le journalise dans le rapport de run (`history_rewritten: true`).

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
Statut par étape, tickers en échec, nombre de barres ajoutées, durée, avertissements qualité.

## 7. Export dashboard — `dashboard/public/data/` (non commité)
| Fichier | Contenu | Taille cible |
|---|---|---|
| `manifest.json` | dates, liste tickers, stratégies, version | < 10 Ko |
| `overview.json` | leaderboard, derniers signaux, KPIs | < 100 Ko |
| `tickers/{SYMBOL}.json` | OHLCV + indicateurs (SMA20/50/200, RSI, Bollinger) + marqueurs de signaux | < 500 Ko |
| `portfolios/{strategy_id}.json` | courbe d'equity, positions, trades, drawdown | < 200 Ko |
| `models.json` | model cards, métriques OOS, distribution des random traders | < 200 Ko |
| `health.json` | fraîcheur des données, derniers runs | < 20 Ko |
