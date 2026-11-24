# Roadmap

## Milestones

### M0 — Fondations
Squelette, CI, config. **Sortie** : CI verte, `th version`, dashboard « hello » buildé.

### M1 — Données en ligne (premier dashboard public)
Ingestion quotidienne, validation, export partiel, dashboard Overview + Ticker (chandeliers), déploiement Pages.
**Sortie** : chaque soir de bourse, le dashboard public montre les chandeliers à jour.

### M2 — Backtest & baselines
Features, moteur de backtest, Buy & Hold, Random Traders (Monte-Carlo), SMA crossover.
**Sortie** : page Models avec la distribution des random traders et les baselines.

### M3 — IA & paper trading
LightGBM walk-forward, registre + promotion, signaux quotidiens, portefeuilles fictifs, entraînement hebdo.
**Sortie** : portefeuilles fictifs qui avancent chaque jour, signaux expliqués sur le dashboard.

### M4 — Finitions
Pages Portfolios/Health complètes, e2e, Lighthouse, documentation.

## Features

| ID | Feature | Milestone | Dépend de | Statut |
|---|---|---|---|---|
| F00 | Bootstrap du dépôt | M0 | — | ✔️ Done |
| F01 | Ingestion yFinance | M1 | F00 | ✔️ Done |
| F02 | Qualité des données | M1 | F01 | 🔍 Verifying |
| F08 | Export dashboard (partiel) | M1 | F01, F02 | 📝 Draft |
| F09 | Dashboard (Overview, Ticker) | M1 | F08 | 📝 Draft |
| F10 | Orchestration (daily, deploy, ci) | M1 | F01, F02, F08 | 📝 Draft |
| F03 | Features & labels | M2 | F01 | 📝 Draft |
| F04 | Moteur de backtest & métriques | M2 | F01 | 📝 Draft |
| F05 | Baselines | M2 | F04 | 📝 Draft |
| F06 | Modèles IA & registre | M3 | F03, F04, F05 | 📝 Draft |
| F07 | Signaux & paper trading | M3 | F04–F06 | 📝 Draft |
| F08 | Export dashboard (complet) | M3 | F04–F07 | 📝 Draft |
| F09 | Dashboard (Portfolios, Models, Health) | M3/M4 | F08 | 📝 Draft |
| F10 | Orchestration (weekly-train, backfill) | M3 | F06 | 📝 Draft |

Ordre conseillé : F00 → F01 → F02 → F08(partiel) → F10(daily+deploy) → F09(M1) → F04 → F03 → F05 → F06 → F07 → reste.
Démarrer le cron quotidien **dès M1** : chaque jour d'historique live accumulé tôt rend le paper trading plus parlant ensuite.

## Backlog v2+ (idées d'extension)
- **Univers & marchés** : actions EU (Euronext, multi-devises EUR/USD), ETF sectoriels, crypto (marché 7j/7 → calendrier dédié).
- **Modèles** : régression logistique (baseline linéaire), régression du rendement 20 j, LSTM/TCN, RL (PPO), ensemble/méta-modèle, optimisation de portefeuille (risk parity, Markowitz sur rendements prédits).
- **Signaux externes** : sentiment de news (RSS + modèle de sentiment léger), données macro (FRED), VIX.
- **Gestion du risque** : stop-loss/take-profit simulés, sizing par volatilité (ATR), contrainte de drawdown.
- **Alertes** : Issue GitHub automatique quand un signal fort apparaît, notification Telegram/Discord (secret optionnel).
- **Explicabilité** : page « pourquoi ce signal » avec SHAP, analyse de régime de marché (haussier/baissier/latéral).
- **Dashboard** : comparateur de tickers, simulateur « et si j'avais suivi la stratégie X depuis le … », export CSV.
- **Maintenance** : Dependabot (SHA des actions, `uv.lock`, `package-lock.json`).
- **Qualité** : détection de dérive des features (PSI), suivi de la calibration live vs backtest.
