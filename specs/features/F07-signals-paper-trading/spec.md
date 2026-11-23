# F07 — Signaux quotidiens & portefeuilles fictifs

- **Statut** : 📝 Draft
- **Milestone** : M3
- **Dépend de** : F04, F05, F06
- **Contrats** : §3, §4

## Objectif
Chaque soir de bourse, chaque stratégie active produit ses signaux et son portefeuille fictif avance d'une séance.

## Exigences
- **R1** `th signal` DOIT, pour chaque stratégie de `config/strategies.yaml` (`active: true`), appeler `decide` à la dernière séance disponible et écrire `data/signals/{date}.json` + `latest.json`.
- **R2** `th paper` DOIT charger `data/portfolios/{id}.json`, reprendre le moteur F04 en mode incrémental jusqu'à la dernière séance, et réécrire le fichier.
- **R3** QUAND une stratégie n'a pas de fichier portefeuille, le système DOIT l'initialiser à la date `inception` configurée (défaut : prochaine séance) avec `initial_capital`. **Pas de backfill rétroactif** des portefeuilles fictifs : ils mesurent la performance *live*, distincte du backtest.
- **R4** QUAND le champion d'une famille ML change, le portefeuille de la stratégie continue (même `strategy_id`) et le changement est journalisé comme événement `model_switch` dans le portefeuille.
- **R5** Les deux commandes DOIVENT être idempotentes pour une date donnée.
- **R6** Les ordres décidés en `t` apparaissent dans `trades` à la date `t+1` (exécution à l'open, P1) ; en attendant, ils sont stockés dans `pending_orders`.

## Critères d'acceptation
- [ ] Relancer `th paper` deux fois le même jour ne change pas le fichier.
- [ ] Sur 10 séances simulées, le portefeuille obtenu en incrémental == backtest F04 sur la même période depuis `inception`.
- [ ] `latest.json` valide le schéma et contient une entrée par (stratégie active × ticker).
