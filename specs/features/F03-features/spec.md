# F03 — Feature engineering & labels

- **Statut** : 📝 Draft
- **Milestone** : M2
- **Dépend de** : F01

## Objectif
Construire, à partir des prix bruts, une matrice de features et des labels **sans look-ahead** (P1),
réutilisable par les stratégies ML, l'heuristique SMA et l'export dashboard.

## Exigences
- **R1** `features.indicators` DOIT fournir des fonctions pures et vectorisées : rendements (1, 5, 20 j), log-rendements,
  SMA/EMA (10, 20, 50, 200), ratio prix/SMA, RSI(14), MACD(12,26,9), Bollinger(20, 2σ) %B et largeur,
  ATR(14), volatilité réalisée (20 j), volume relatif (volume / moyenne 20 j), drawdown depuis plus haut 52 sem.
- **R2** Les features de marché DOIVENT inclure le rendement et la volatilité du benchmark (SPY) aux mêmes dates.
- **R3** Toute feature à la date `t` DOIT être calculable uniquement avec les barres `<= t`.
- **R4** `features.labels` DOIT produire le label `dir_h` = 1 si `adj_close[t+h] / adj_close[t] - 1 > seuil` sinon 0 (h=5, seuil=0 par défaut, paramétrables) ; les lignes sans futur connu ont un label `NaN`.
- **R5** `features.builder.build(market_data, until)` DOIT renvoyer un `DataFrame` indexé `(date, symbol)` ; les lignes de warm-up (NaN) sont supprimées.
- **R6** Les features NE DOIVENT PAS être commitées ; elles sont recalculées (temps cible < 30 s pour 20 tickers × 15 ans).

## Critères d'acceptation
- [ ] Test de propriété (hypothesis) : pour toute date `t`, `build(data, until=t)` et `build(data[:t+k], until=t)` donnent des features identiques à `t` (k ∈ [1, 50]).
- [ ] RSI, MACD, Bollinger comparés à des valeurs de référence (fixtures calculées à la main / tableur) à 1e-6.
- [ ] Le label n'est jamais présent pour les `h` dernières séances.
