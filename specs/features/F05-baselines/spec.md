# F05 — Stratégies baselines

- **Statut** : 📝 Draft
- **Milestone** : M2
- **Dépend de** : F04
- **Principe clé** : P3

## Objectif
Fournir les références contre lesquelles tout modèle d'IA est jugé.

## Stratégies
| id | Description |
|---|---|
| `buy_hold` | Achète l'univers en équipondéré au 1er jour, ne rééquilibre jamais. |
| `buy_hold_spy` | 100 % benchmark (SPY). |
| `random_s{seed}` | Chaque séance, avec proba `p_trade` (défaut 0,1) par ticker, tire aléatoirement BUY/SELL ; poids cibles équipondérés sur les positions tenues. |
| `sma_cross` | Long un ticker si SMA50 > SMA200, sinon cash. Équipondéré entre tickers éligibles. |

## Exigences
- **R1** Chaque stratégie DOIT implémenter le protocole `Strategy` (F04) et être enregistrée dans un registre `strategies.REGISTRY` via son `id`.
- **R2** `random_trader` DOIT utiliser un `numpy.random.Generator` seedé, dérivé de `(seed, date)` pour que le résultat d'une séance ne dépende pas de l'historique d'appels (reproductibilité en mode incrémental).
- **R3** `th backtest random --n 100` DOIT produire la **distribution** des métriques sur N seeds (percentiles 5/25/50/75/95) stockée pour l'export `models.json`.
- **R4** Le système DOIT fournir `random_percentile(metric_value, distribution)` utilisé pour classer chaque stratégie.
- **R5** Le paper trading DOIT suivre un seul random trader « représentatif » (`random_s42`) ; la distribution complète n'est recalculée qu'au backtest hebdomadaire.

## Critères d'acceptation
- [ ] `random_s42` sur la même période donne deux fois exactement la même courbe.
- [ ] La médiane de 100 random traders sans frais est proche de Buy & Hold (écart de CAGR < 3 pts) sur fixture 10 ans — test de cohérence.
- [ ] `sma_cross` ne prend aucune position pendant les 200 premières séances.
