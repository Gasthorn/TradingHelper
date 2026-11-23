# F08 — Export des données pour le dashboard

- **Statut** : 📝 Draft
- **Milestone** : M1 (partiel : manifest, tickers, health) puis M3 (complet)
- **Dépend de** : F01, F02 ; F04–F07 pour les sections correspondantes
- **Contrat** : §7

## Objectif
Transformer les données du dépôt en fichiers JSON compacts, pré-calculés et optimisés pour le navigateur.

## Exigences
- **R1** `th export --out dashboard/public/data` DOIT produire les fichiers listés au §7, chacun validé par son schéma.
- **R2** `tickers/{SYMBOL}.json` DOIT contenir OHLCV (format colonnes), SMA20/50/200, Bollinger, RSI14, volume, et les marqueurs de signaux de chaque stratégie (date, action, confiance).
- **R3** QUAND une section dépend d'une feature non encore livrée (ex. pas de modèles), l'export DOIT produire la section vide plutôt qu'échouer.
- **R4** Les nombres DOIVENT être arrondis (prix 2–4 déc., ratios 4 déc.) et le JSON minifié pour respecter les tailles cibles.
- **R5** `manifest.json` DOIT contenir `generated_at`, `data_as_of`, `git_sha`, `schema_version`, et la liste des fichiers avec leur hash (cache-busting côté front).

## Critères d'acceptation
- [ ] Sur dépôt avec seulement des prix (M1) : export OK, sections modèles/portefeuilles vides.
- [ ] Tailles de fichiers sous les cibles pour 20 tickers × 15 ans.
- [ ] Les types TS générés depuis `schemas/` compilent avec le dashboard.
