# Vision produit

## Problème
Un investisseur particulier veut une aide à la décision quotidienne sur une liste d'actions suivies,
sans payer d'infrastructure, avec une évaluation honnête : « est-ce que ce modèle fait mieux que le hasard
ou que simplement acheter et garder ? ».

## Solution
**TradingHelper** est un projet 100 % GitHub :

1. **GitHub Actions** récupère chaque soir de bourse les cours (OHLCV) via yFinance et les commite en JSON.
2. Des **stratégies** (baselines + modèles d'IA) sont entraînées et évaluées en walk-forward sur cet historique.
3. Chaque stratégie gère un **portefeuille fictif** (paper trading) mis à jour quotidiennement.
4. Chaque jour, des **signaux** (acheter / conserver / vendre + confiance) sont publiés.
5. Un **dashboard statique sur GitHub Pages** affiche chandeliers, signaux, portefeuilles et classement des modèles.

## Utilisateurs
- **Moi (owner)** : configure la watchlist, consulte le dashboard, lance des entraînements manuels.
- **Visiteur** : consulte le dashboard public en lecture seule.

## Périmètre v1 (MVP)
- Univers : ~20 tickers US en USD (configurable), fréquence **journalière**.
- Baselines : Buy & Hold (équipondéré), Random Trader (Monte-Carlo, N=100 seeds), SMA crossover (heuristique de référence).
- Modèle IA v1 : classifieur gradient boosting (LightGBM) prédisant la direction à horizon 5 jours.
- Portefeuilles fictifs : 10 000 USD de capital initial par stratégie, frais et slippage simulés.
- Dashboard : vue d'ensemble, fiche ticker (chandeliers + indicateurs + signaux), portefeuilles, comparaison des modèles, santé des données.

## Hors périmètre v1 (backlog)
- Intraday, options, crypto, multi-devises (EUR).
- Passage d'ordres réels chez un broker (**jamais automatisé** dans ce projet).
- Sentiment de news / LLM, Reinforcement Learning, LSTM/Transformers → voir `roadmap.md` (v2+).
- Alertes (Issues GitHub, Telegram, e-mail).

## Critères de succès
- Le pipeline quotidien tourne 20 jours de bourse consécutifs sans intervention.
- Le dashboard se charge en < 2 s (données < 5 Mo transférées sur la page d'accueil).
- Chaque modèle affiché a une comparaison chiffrée vs baselines, avec son percentile dans la distribution des random traders.
