# F04 — Moteur de backtest & métriques

- **Statut** : 📝 Draft
- **Milestone** : M2
- **Dépend de** : F01, F03 (indirectement)
- **Principes clés** : P1, P2

## Objectif
Un moteur unique, événementiel jour par jour, qui simule une stratégie sur une période et produit
un portefeuille conforme au contrat §3 ainsi que des métriques. Il sert **aussi** au paper trading quotidien (F07).

## Exigences
- **R1** `engine.run(strategy, market_data, start, end, config, state=None) -> PortfolioState` DOIT itérer séance par séance :
  1. construire `DecisionContext` avec une vue **tronquée** des données `<= t` ;
  2. appeler `strategy.decide(ctx)` → `TargetWeights` ;
  3. générer les ordres de rééquilibrage ; les exécuter à l'**open de `t+1`** ;
  4. valoriser le portefeuille à la clôture.
- **R2** QUAND `state` est fourni, le moteur DOIT reprendre à partir de cet état (mode incrémental pour le paper trading).
- **R3** Le moteur DOIT appliquer des coûts configurables (`config/backtest.yaml`) : commission fixe + proportionnelle, slippage en bps, quantités entières (pas de fractions en v1).
- **R4** Le moteur DOIT ignorer les ordres de rééquilibrage dont la variation de poids est < `min_rebalance` (défaut 2 %) pour limiter le turnover.
- **R5** Le moteur NE DOIT PAS permettre de cash négatif ni de position négative (vente limitée à la quantité détenue ; achat limité au cash disponible).
- **R6** `metrics.compute(equity_curve, trades, benchmark)` DOIT calculer : rendement total, CAGR, volatilité annualisée, Sharpe (rf=0 par défaut, paramétrable), Sortino, max drawdown et durée, Calmar, hit rate des trades, turnover annuel, exposition moyenne, bêta et alpha vs benchmark, excès de rendement vs Buy & Hold.
- **R7** `walk_forward.run(strategy_factory, data, train_years, test_months, step_months)` DOIT enchaîner fit/test en fenêtres glissantes et concaténer les segments out-of-sample.
- **R8** Le moteur DOIT être déterministe pour un `seed` donné.

## Critères d'acceptation
- [ ] **Test anti-look-ahead générique** : une `SpyStrategy` qui tente d'accéder à `ctx.data` après `ctx.date` lève une exception ; paramétré sur toutes les stratégies enregistrées.
- [ ] Test de propriété : invariant `cash + valeur positions == equity` à chaque séance ; cash ≥ 0.
- [ ] Buy & Hold d'un seul ticker sans frais reproduit le rendement `adj_close` à 1e-9 près.
- [ ] Un backtest 20 tickers × 10 ans s'exécute en < 20 s.
- [ ] `run(…, end=T)` puis reprise incrémentale jusqu'à `T+10` == `run(…, end=T+10)` en une fois (P2).
