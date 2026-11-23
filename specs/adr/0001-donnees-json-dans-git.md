# 0001 — Stocker les données de marché en JSON dans le dépôt git

- **Date** : 2026-11-23
- **Statut** : Acceptée
- **Features concernées** : F01, F08, F10

## Contexte
Le projet doit rester gratuit et 100 % GitHub. Les données doivent être consultables, versionnées et accessibles
aux workflows comme au dashboard.

## Options envisagées
1. **JSON par ticker dans `main`** — simple, diffable, lisible ; croissance du dépôt limitée (~450 Ko/an pour 20 tickers).
2. **Parquet** — compact et rapide, mais binaire (diffs illisibles, chaque mise à jour réécrit tout le fichier dans l'historique git).
3. **Branche orpheline `data`** — sépare code et données, plus complexe à orchestrer.
4. **Stockage externe (S3, Supabase…)** — sort du « 100 % GitHub », nécessite des secrets.

## Décision
Option 1, avec format « une barre par ligne » (append = 1 ligne de diff). Parquet éventuellement en cache CI
(`actions/cache`) si les temps de chargement deviennent un problème.

## Conséquences
- Revoir la décision (option 3) si l'univers dépasse ~200 tickers ou si le dépôt dépasse 500 Mo.
- Les données dérivées ne sont jamais commitées.
