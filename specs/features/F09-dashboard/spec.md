# F09 — Dashboard GitHub Pages

- **Statut** : 📝 Draft
- **Milestone** : M1 (Overview + Ticker) puis M3/M4 (reste)
- **Dépend de** : F08

## Objectif
Un site statique, rapide, lisible sur mobile, qui rend visibles marché, signaux, portefeuilles et performance des modèles.

## Pages
| Route (hash) | Contenu |
|---|---|
| `#/` **Overview** | Date des données, bandeau P8, KPIs (meilleure stratégie 30 j, equity totale par stratégie), tableau des derniers signaux filtrable, mini-sparklines par ticker. |
| `#/ticker/:symbol` | Chandeliers (lightweight-charts) + volume ; overlays SMA/Bollinger activables ; panneau RSI ; marqueurs BUY/SELL par stratégie (sélecteur) ; fiche signal du jour avec explication des features. Sélecteur de période (1M, 6M, 1A, 5A, Max). |
| `#/portfolios` | Courbes d'equity superposées (toutes stratégies + baselines, base 100), drawdown, tableau des métriques live. |
| `#/portfolio/:id` | Equity, positions actuelles (répartition), journal des trades, événements `model_switch`. |
| `#/models` | Leaderboard OOS (Sharpe, CAGR, MaxDD, percentile random) ; histogramme de la distribution des random traders avec la position de chaque stratégie ; model cards ; courbe de calibration. |
| `#/health` | Fraîcheur par ticker, derniers runs (statut par étape), avertissements qualité. |

## Exigences
- **R1** Le site DOIT être 100 % statique, routé par hash (compatible Pages sans 404.html), sans backend.
- **R2** Le site DOIT charger `manifest.json` puis les fichiers à la demande (lazy par page / ticker).
- **R3** Le thème DOIT supporter clair/sombre (`prefers-color-scheme` + bascule), couleurs haussier/baissier accessibles (pas seulement rouge/vert : ajouter forme/libellé).
- **R4** Le site DOIT être utilisable à 375 px de large.
- **R5** Le bandeau d'avertissement (P8) DOIT être visible sur toutes les pages.
- **R6** Le site DOIT afficher clairement la date `data_as_of` et un état « données périmées » si > 3 séances.
- **R7** Le `base` Vite DOIT être configurable (`/TradingHelper/`) pour fonctionner sous `https://<user>.github.io/TradingHelper/`.
- **R8** Tests : unitaires (Vitest) pour `lib/` (formatage, calculs base 100) ; un test e2e smoke (Playwright) qui charge chaque route sur des données fixtures.

## Critères d'acceptation
- [ ] Lighthouse performance ≥ 90 sur Overview (mobile).
- [ ] Toutes les routes s'affichent sans erreur console avec les fixtures M1 (sections vides gérées).
- [ ] Les marqueurs de signaux apparaissent aux bonnes dates sur le graphique.
