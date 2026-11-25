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
Section `validate` (F02 R7–R8) = liste d'exécutions de `th validate`, ajoutée si le rapport de la séance existe déjà
ou s'il y a une violation bloquante :
```json
{
  "schema_version": 1,
  "session_date": "2026-11-23",
  "validate": [
    {
      "started_at": "2026-11-23T22:32:15Z",
      "finished_at": "2026-11-23T22:32:16Z",
      "duration_s": 0.9,
      "args": { "symbols": null, "all_history": false },
      "exit_code": 1,
      "files_checked": 21,
      "violations": [
        { "symbol": "AAPL", "date": "2026-11-20", "rule": "ohlc_inconsistent",
          "detail": "2026-11-20 : low 229.6 / high 229.0 incompatibles avec open 231.0 et close 232.4" }
      ],
      "warnings": [
        { "symbol": "MSFT", "rule": "missing_session", "start": "2026-11-17", "end": "2026-11-18", "value": 2 },
        { "symbol": "NVDA", "rule": "large_move", "start": "2026-11-23", "end": "2026-11-23", "value": 0.6 },
        { "symbol": "TSLA", "rule": "stale", "start": null, "end": null, "value": 5 }
      ]
    }
  ]
}
```
Violations (`exit_code: 1` si et seulement s'il y en a) : `unreadable`, `schema`, `symbol_mismatch`, `empty_bars`,
`dates_not_increasing`, `non_session_date`, `after_last_session`, `non_positive_price`, `negative_volume`,
`ohlc_inconsistent`, `not_rounded` ; `symbol` = nom du fichier, `date` à `null` pour une erreur de fichier ou d'en-tête.
Avertissements : `missing_session` (plage, `value` = nombre de séances), `large_move` (`value` = variation simple),
`zero_volume`, `stale` (`value` = séances de retard), `missing_file` ; `start`/`end` à `null` pour `stale` et `missing_file`.

Les sections des étapes suivantes (`signal`, etc.) sont définies par leurs features.

## 7. Export dashboard — `dashboard/public/data/` (non commité)
Produit par `th export` (F08). Modèles pydantic `ManifestFile`, `TickerFile`, `OverviewFile`, `HealthFile` (M1),
`PortfolioExportFile`, `ModelsFile` (M3) dans `schemas.py` ; types TS générés dans `dashboard/src/types/`.

| Fichier | Contenu | Taille cible | Milestone |
|---|---|---|---|
| `manifest.json` | dates, tickers, stratégies, version, hash des fichiers | < 10 Ko | M1 |
| `overview.json` | dernier cours + sparkline par ticker ; leaderboard, derniers signaux, KPIs | < 100 Ko | M1 (leaderboard, signaux, KPIs vides) / M3 |
| `tickers/{SYMBOL}.json` | OHLCV + indicateurs (SMA20/50/200, Bollinger, RSI14) + marqueurs de signaux | < 500 Ko | M1 |
| `health.json` | fraîcheur par ticker, derniers runs, avertissements qualité | < 20 Ko | M1 |
| `portfolios/{strategy_id}.json` | courbe d'equity, drawdown, positions, trades, `model_switch`, métriques live | < 200 Ko | M3 |
| `models.json` | model cards, métriques OOS, distribution des random traders, calibration | < 200 Ko | M3 |

**Format commun** : JSON minifié (séparateurs `,` et `:`), UTF-8, champ `schema_version` (1) dans chaque fichier ;
`null` pour une valeur indisponible (jamais `NaN`). Arrondis : prix et indicateurs de prix 4 décimales ; RSI 2 ;
ratios, rendements, poids, confiances, métriques 4 ; montants 2 ; volumes et quantités entiers. Les exemples ci-dessous
sont indentés pour la lecture.

### `manifest.json`
```json
{
  "schema_version": 1,
  "generated_at": "2026-11-23T22:50:12Z",
  "data_as_of": "2026-11-23",
  "git_sha": "430115d4c1f0e2b3a49587c6d1e0f2a3b4c5d6e7",
  "currency": "USD",
  "benchmark": "SPY",
  "tickers": [
    { "symbol": "AAPL", "name": "Apple Inc.", "sector": "Information Technology", "benchmark": false,
      "first_date": "2010-01-04", "last_date": "2026-11-23" },
    { "symbol": "SPY", "name": "SPY", "sector": null, "benchmark": true,
      "first_date": "2010-01-04", "last_date": "2026-11-23" }
  ],
  "strategies": [],
  "files": [
    { "path": "health.json", "sha256": "9f2c4e1a7b3d5c60", "bytes": 4210 },
    { "path": "tickers/AAPL.json", "sha256": "1a2b3c4d5e6f7a8b", "bytes": 401233 }
  ]
}
```
`data_as_of` = plus petite dernière date des symboles exportés (univers + benchmark ayant un fichier), `null` sinon.
`git_sha` = `TH_GIT_SHA`, sinon `git rev-parse HEAD`, sinon `GITHUB_SHA`, sinon `null` (F08 R11, F10 R8). `files` : tous les fichiers produits sauf le manifest,
triés par `path` ; `sha256` = 16 premiers caractères hexadécimaux. M3 : `strategies` =
`[{ "id": "lgbm_dir5_v3", "kind": "model", "model_id": "lgbm_dir5_20261122_ab12cd", "sharpe_oos": 1.1 }]`
(`kind ∈ {baseline, model}`, `model_id` à `null` pour une baseline).

### `tickers/{SYMBOL}.json`
Format colonnes : chaque tableau de `series` a la même longueur ; valeurs de warm-up à `null`.
```json
{
  "schema_version": 1,
  "symbol": "AAPL",
  "series": {
    "date":     ["2026-11-20", "2026-11-23"],
    "open":     [228.1, 231.0],
    "high":     [231.45, 233.12],
    "low":      [227.8, 229.6],
    "close":    [230.95, 232.4],
    "volume":   [51234000, 48765000],
    "sma20":    [226.418, 226.9905],
    "sma50":    [221.0712, 221.3304],
    "sma200":   [205.5521, 205.7413],
    "bb_upper": [233.1022, 233.8817],
    "bb_lower": [219.7338, 220.0993],
    "rsi14":    [61.42, 63.87]
  },
  "markers": [
    { "date": "2026-11-20", "strategy_id": "lgbm_dir5_v3", "action": "BUY", "confidence": 0.67 }
  ]
}
```
OHLC ajustés des splits (tels que stockés, §2). Indicateurs sur `close`, fenêtres passées uniquement (P1) :
SMA(20, 50, 200), Bollinger(20, 2σ, écart-type de population), RSI(14) de Wilder. `markers` : signaux BUY/SELL de
`data/signals/*.json` (HOLD exclus), triés par date puis `strategy_id` ; vide en M1.

### `overview.json`
```json
{
  "schema_version": 1,
  "data_as_of": "2026-11-23",
  "tickers": [
    { "symbol": "AAPL", "last_close": 232.4, "change_1d": 0.0063, "spark": [221.3, 222.05, 232.4] }
  ],
  "leaderboard": [],
  "latest_signals": [],
  "kpis": { "best_strategy_30d": null }
}
```
`spark` : 60 dernières clôtures au plus ; `change_1d` à `null` s'il n'y a qu'une barre. M3 : ligne de `leaderboard` =
`{ "strategy_id", "kind", "equity", "return_30d", "sharpe_oos", "random_percentile" }` (baselines toujours présentes, P3) ;
`latest_signals` = signaux de `latest.json` (§4) enrichis de `model_id` et `sharpe_oos` (P8).

### `health.json`
```json
{
  "schema_version": 1,
  "last_session": "2026-11-23",
  "tickers": [
    { "symbol": "AAPL", "last_date": "2026-11-23", "sessions_behind": 0, "stale": false },
    { "symbol": "TSLA", "last_date": null, "sessions_behind": null, "stale": true }
  ],
  "runs": [
    {
      "session_date": "2026-11-23",
      "ingest": { "exit_code": 0, "ok": 20, "unchanged": 0, "failed": 1, "history_rewritten": ["AAPL"] },
      "validate": { "exit_code": 0, "violations": 0, "warnings": 2 }
    }
  ],
  "quality_warnings": [
    { "symbol": "NVDA", "rule": "large_move", "start": "2026-11-23", "end": "2026-11-23", "value": 0.6 }
  ],
  "quality_warnings_truncated": 0
}
```
`last_session` = `S` au moment de l'export. `tickers` : univers + benchmark ; `stale` comme F02 (`last_date < S − 3
séances`, `true` sans fichier). `runs` : 10 rapports les plus récents, par `session_date` décroissante, résumés depuis la
dernière exécution de chaque section (`null` si absente). `quality_warnings` : avertissements (format §6) de la dernière
exécution `validate` du rapport le plus récent qui en contient une, 100 au plus.

### `portfolios/{strategy_id}.json` et `models.json` (M3)
Format détaillé à fixer avant l'implémentation M3 de F08, une fois réglés les pré-requis listés dans la spec F08
(`model_switch` et `pending_orders` en §3, calibration en §5, stockage de la distribution des random traders par F05).
