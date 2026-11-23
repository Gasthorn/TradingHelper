# Constitution du projet

Principes **non négociables**. Toute spec, tout plan et tout code doivent les respecter.
En cas de conflit entre une spec de feature et ce document, ce document l'emporte.

## P1 — Zéro fuite du futur (no look-ahead)
- Une décision prise pour la séance `t` n'utilise **que** des données dont la date est `<= t` (clôture).
- L'exécution d'un ordre décidé en `t` se fait au **prix d'ouverture de `t+1`** (+ slippage).
- Toute normalisation / scaler / sélection de features est **ajustée uniquement sur la fenêtre d'entraînement**.
- Chaque stratégie a un test automatisé « anti-look-ahead » (voir F04).

## P2 — Un seul moteur pour le backtest et le paper trading
- Backtest historique et portefeuille fictif quotidien passent par **le même code** (`backtest.engine`).
- Aucune logique de décision n'existe en double.

## P3 — Toujours battre les baselines, sinon le dire
- Chaque modèle est évalué contre **Buy & Hold** et une **distribution de Random Traders** (Monte-Carlo).
- Un modèle n'est « promu » que s'il bat le champion actuel ET la médiane des random traders sur la période out-of-sample.
- Le dashboard affiche toujours les baselines à côté des modèles.

## P4 — Reproductibilité
- Toute exécution stochastique prend un `seed` explicite, journalisé dans les sorties.
- Chaque modèle entraîné a une fiche (`model_card.json`) : hash des données, période, hyperparamètres, version du code (SHA git), métriques.
- Les dépendances sont verrouillées (`uv.lock`, `package-lock.json`).

## P5 — Les données sont versionnées, lisibles et diffables
- Les données brutes sont en JSON **une barre par ligne** pour que les diffs git restent lisibles.
- Les données brutes sont **append-only** : une correction historique passe par un commit explicite journalisé.
- Tout fichier JSON produit respecte un **JSON Schema** du dossier `schemas/`.
- Les données dérivées (features, export dashboard) ne sont **pas** commitées : elles sont recalculées.

## P6 — Frugalité CI
- Tout le pipeline tourne sur un runner GitHub `ubuntu-latest` standard (CPU, < 30 min pour le daily, < 2 h pour l'entraînement).
- Pas de GPU, pas de service payant, pas de secret obligatoire pour la v1.

## P7 — Robustesse aux pannes de la source
- yfinance est non officiel : toute erreur réseau est retentée (backoff), un ticker en échec n'empêche pas les autres.
- Un run partiellement en échec produit un rapport, ne corrompt jamais les données existantes (écriture atomique).

## P8 — Transparence et avertissement
- Le dashboard affiche en permanence : « Outil expérimental et éducatif. Ceci n'est pas un conseil en investissement. »
- Chaque recommandation affiche sa confiance, le modèle qui l'a produite et sa performance historique.

## P9 — Qualité de code
- Python ≥ 3.12, typage strict (`mypy --strict` sur `src/`), `ruff` (lint + format).
- TypeScript strict pour le dashboard.
- Toute feature livrée a des tests ; la couverture de `backtest/` et `strategies/` est ≥ 90 %.
- Pas de notebook dans `src/` ; les explorations vont dans `research/` et ne sont pas importées par le pipeline.
