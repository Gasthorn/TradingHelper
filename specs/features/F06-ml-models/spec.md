# F06 — Modèles d'IA : entraînement, évaluation, registre

- **Statut** : 📝 Draft
- **Milestone** : M3
- **Dépend de** : F03, F04, F05
- **Principes clés** : P1, P3, P4, P6

## Objectif
Entraîner chaque semaine des modèles prédictifs, les évaluer honnêtement en walk-forward,
et ne promouvoir que ceux qui battent les baselines.

## Famille v1 : `lgbm_dir5`
- Classifieur LightGBM sur les features F03, label `dir_5`.
- Modèle **poolé** (un seul modèle pour tous les tickers, `symbol` non utilisé comme feature en v1).
- Politique de décision : `p = P(hausse à 5 j)` ; BUY si `p > 0.55`, SELL si `p < 0.45`, sinon HOLD ;
  poids cibles ∝ `(p - 0.5)` sur les tickers BUY, plafonnés à `max_weight` (défaut 15 %), somme ≤ 1.
- Seuils et `max_weight` configurables dans `config/strategies.yaml`.

## Exigences
- **R1** `th train --family lgbm_dir5` DOIT : construire features/labels ; lancer un walk-forward (train 5 ans glissants, test 3 mois, pas 3 mois) ; entraîner le modèle final sur toutes les données labellisées ; écrire `models/registry/{model_id}/model.txt` + `model_card.json` (contrat §5).
- **R2** La validation interne (early stopping, tuning) DOIT utiliser un découpage **temporel** avec un *embargo* de `h` séances entre train et validation (pas de `KFold` mélangé).
- **R3** Les métriques OOS DOIVENT inclure les métriques financières F04 (via le moteur, frais inclus) ET les métriques ML (AUC, log-loss, hit rate, calibration par décile).
- **R4** `th promote` DOIT comparer le candidat au champion de la famille sur la **même** période OOS ; promotion SI Sharpe candidat > Sharpe champion ET `random_percentile(sharpe) >= 0.75` ET `excess_vs_buy_hold > 0`. Sinon statut `candidate` conservé, puis `retired` après 4 semaines.
- **R5** Un modèle sérialisé DOIT peser < 2 Mo ; seuls les 5 derniers modèles par famille + le champion sont conservés dans le dépôt.
- **R6** L'entraînement hebdomadaire complet DOIT tenir en < 60 min sur `ubuntu-latest`.
- **R7** La stratégie `ml_classifier` DOIT charger le champion du registre et fournir dans ses signaux les 5 principales contributions (`pred_contrib=True` de LightGBM).
- **R8** L'architecture DOIT permettre d'ajouter une famille (ex. `logreg_dir5`, `lgbm_ret20_reg`) en ajoutant une classe et une entrée de config, sans modifier le moteur.

## Critères d'acceptation
- [ ] Sur une fixture synthétique où le label est une fonction déterministe d'une feature passée, AUC OOS > 0,95 (le pipeline sait apprendre).
- [ ] Sur une marche aléatoire synthétique, AUC OOS ∈ [0,45 ; 0,55] et le modèle n'est **pas** promu (le pipeline ne s'illusionne pas).
- [ ] Deux entraînements avec le même seed et les mêmes données produisent le même `model.txt`.
- [ ] `model_card.json` validé par son schéma, contient `git_sha` et `data_hash`.

## Backlog (v2+)
`logreg_dir5` (baseline linéaire), régression de rendement, modèles séquentiels (LSTM/TCN), RL (PPO via stable-baselines3),
features de sentiment news, méta-modèle d'ensemble.
