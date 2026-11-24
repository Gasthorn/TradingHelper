# Architecture

## Vue d'ensemble

```
                     ┌──────────────────────── GitHub Actions ─────────────────────────┐
                     │                                                                  │
 yFinance ──► [daily.yml] ingest ─► validate ─► features ─► signal ─► paper-trade ──┐   │
                     │      │                                   ▲                  │   │
                     │      ▼ commit                            │ modèles promus   │   │
                     │  data/raw/prices/*.json            models/registry/         │   │
                     │  data/portfolios/*.json                  ▲                  │   │
                     │  data/signals/*.json                     │                  │   │
                     │                                [weekly-train.yml]           │   │
                     │                        features ─► train ─► walk-forward    │   │
                     │                                   ─► compare vs champion    │   │
                     │                                   ─► promote ─► commit      │   │
                     │                                                             ▼   │
                     │                           [deploy-pages.yml] export ─► build ─► Pages
                     └──────────────────────────────────────────────────────────────────┘
                                                                                  │
                                                                                  ▼
                                                     Dashboard statique (Vite + TS + lightweight-charts)
```

## Choix techniques

| Domaine | Choix | Justification |
|---|---|---|
| Langage pipeline | Python 3.12 | Écosystème data/ML |
| Gestion deps | `uv` + `pyproject.toml` + `uv.lock`, backend de build `uv_build` | Rapide en CI, lockfile ; backend natif uv, sans dépendance de build supplémentaire (F00) |
| CLI | `typer` → commande `th` | Une commande par étape, appelée par les workflows |
| Configuration | `config/*.yaml` lus par PyYAML (clés dupliquées refusées), validés par `pydantic` v2 (`extra="forbid"`) | Erreurs explicites fichier + champ ; pas de `pydantic-settings`, aucune surcharge par variables d'environnement n'étant nécessaire (F00) |
| Données | `pandas`, `pyarrow` (en mémoire uniquement) | Standard |
| Source | `yfinance` | Gratuit (non officiel, voir P7) |
| Indicateurs | implémentation maison (`numpy`/`pandas`) | Évite `ta-lib` (binaire C pénible en CI) |
| ML | `scikit-learn`, `lightgbm` | CPU, rapide, modèles légers (< 1 Mo) |
| Validation | `pydantic` v2 + JSON Schema générés | Contrats partagés Python ↔ TS |
| Tests | `pytest`, `hypothesis`, `pytest-socket` | Propriétés (ex. invariants de portefeuille) ; réseau bloqué dans les tests |
| Qualité | `ruff`, `mypy --strict` | P9 |
| Dashboard | Vite + TypeScript + Preact | Statique, léger (~4 Ko), composants pour F09 — décidé en F00 (Q1) |
| Graphiques | `lightweight-charts` (TradingView, Apache-2.0) pour chandeliers ; `uPlot` pour courbes | Performants, petits |
| Hébergement | GitHub Pages via `actions/deploy-pages` | Gratuit |

## Arborescence cible

```
TradingHelper/
├── CLAUDE.md                    # Instructions pour Claude Code
├── README.md
├── pyproject.toml / uv.lock
├── config/
│   ├── universe.yaml            # Tickers suivis + métadonnées
│   ├── backtest.yaml            # Capital, frais, slippage, dates
│   └── strategies.yaml          # Stratégies actives + hyperparamètres
├── schemas/                     # JSON Schemas (générés depuis pydantic) — contrat avec le dashboard
├── data/                        # ✅ commité (P5)
│   ├── raw/prices/{TICKER}.json
│   ├── portfolios/{strategy_id}.json
│   ├── signals/{YYYY-MM-DD}.json + latest.json
│   └── runs/{YYYY-MM-DD}.json   # Rapport d'exécution du pipeline
├── models/
│   └── registry/
│       ├── registry.json        # Index : champion par famille, historique
│       └── {model_id}/          # model.txt (LightGBM), model_card.json
├── src/tradinghelper/
│   ├── cli.py
│   ├── config.py
│   ├── schemas.py               # Modèles pydantic (source de vérité des contrats)
│   ├── data/        ingest.py, source.py, bars.py, storage.py, validate.py, quality.py, calendar.py
│   ├── features/    indicators.py, builder.py, labels.py
│   ├── strategies/  base.py, buy_hold.py, random_trader.py, sma_cross.py, ml_classifier.py
│   ├── backtest/    engine.py, costs.py, metrics.py, walk_forward.py
│   ├── portfolio/   paper.py
│   ├── models/      train.py, registry.py, evaluate.py
│   └── export/      dashboard.py
├── tests/                       # miroir de src/ + fixtures/ (données figées)
├── research/                    # Notebooks d'exploration (non importés)
├── dashboard/                   # App Vite
│   ├── src/ (pages/, components/, lib/data.ts, types/ générés depuis schemas/)
│   └── public/data/             # ❌ non commité, rempli par `th export` en CI
├── specs/                       # SDD (ce dossier)
└── .github/workflows/
    ├── ci.yml
    ├── daily.yml
    ├── weekly-train.yml
    ├── backfill.yml
    └── deploy-pages.yml         # workflow réutilisable (workflow_call)
```

## Abstraction centrale : `Strategy`

```python
class Strategy(Protocol):
    id: str                                  # ex. "buy_hold", "random_s42", "lgbm_dir5_v3"
    def fit(self, history: MarketData, until: date) -> None: ...    # no-op pour les baselines
    def decide(self, ctx: DecisionContext) -> TargetWeights: ...
```

- `DecisionContext` contient **uniquement** les données `<= ctx.date` (vue tronquée fournie par le moteur, P1)
  + l'état courant du portefeuille.
- `TargetWeights` = `dict[ticker, float]` avec `sum <= 1` (le reste en cash), poids `>= 0` (pas de short en v1).
- Le moteur (`backtest.engine`) convertit les poids cibles en ordres, applique frais/slippage, exécute à l'open `t+1`.
- Les **signaux** affichés (BUY/HOLD/SELL + confiance) sont dérivés de la différence entre poids actuels et poids cibles
  et, pour les modèles ML, de la probabilité prédite.

## Convention temporelle
- Toutes les dates sont des **dates de séance** du marché (calendrier NYSE, `pandas_market_calendars`).
- Les cron sont en UTC : `daily.yml` à `30 22 * * 1-5` (après clôture US + marge yfinance).
- Un run sur jour férié détecte « pas de nouvelle séance » et sort proprement (pas de commit).

## Pièges GitHub connus (à gérer)
- Un push fait avec `GITHUB_TOKEN` **ne déclenche pas** d'autres workflows → le déploiement Pages est appelé
  explicitement comme job (`workflow_call`) à la fin de `daily.yml` et `weekly-train.yml`.
- Les workflows `schedule` sont désactivés après 60 jours sans activité du dépôt → les commits quotidiens suffisent,
  mais `daily.yml` doit aussi accepter `workflow_dispatch`.
- `concurrency: group: data-writer` partagé entre tous les workflows qui commitent, pour éviter les conflits de push.
- Les commits du bot utilisent `github-actions[bot]` et un message préfixé `data:` / `model:`.
- Permissions minimales par workflow (`contents: write` seulement où nécessaire ; `pages: write`, `id-token: write` pour le déploiement).

## Volumétrie estimée
- 1 barre ≈ 90 octets → 20 tickers × 10 ans ≈ 4,5 Mo de JSON brut. Croissance ≈ 450 Ko/an. Acceptable pour git.
- Si l'univers dépasse ~200 tickers : basculer les données brutes sur une branche `data` orpheline (décision à documenter en ADR).
