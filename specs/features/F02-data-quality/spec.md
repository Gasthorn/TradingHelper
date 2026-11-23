# F02 — Validation & qualité des données

- **Statut** : 📝 Draft
- **Milestone** : M1
- **Dépend de** : F01

## Objectif
Détecter les données corrompues ou suspectes avant qu'elles n'alimentent les modèles.

## Exigences
- **R1** `th validate` DOIT vérifier chaque fichier prix contre son JSON Schema.
- **R2** Le système DOIT appliquer les règles bloquantes : dates uniques et croissantes ; `low <= min(open, close)` ; `high >= max(open, close)` ; prix > 0 ; volume ≥ 0.
- **R3** Le système DOIT appliquer les règles d'avertissement : séance manquante vs calendrier NYSE ; variation journalière > 40 % ; volume nul ; dernière barre plus vieille que 3 séances (« stale »).
- **R4** QUAND une règle bloquante échoue, `th validate` DOIT sortir en code 1 et le workflow NE DOIT PAS commiter.
- **R5** Le système DOIT écrire le résultat dans la section `validate` du rapport de run et dans l'export `health.json`.
- **R6** `th schemas` DOIT générer `schemas/*.schema.json` depuis `schemas.py` ; la CI DOIT échouer si les fichiers générés diffèrent de ceux commités.

## Critères d'acceptation
- [ ] Fixtures « fichier corrompu » (date dupliquée, high < low) → code 1 avec message pointant ticker + date.
- [ ] Fixture avec saut de +60 % → avertissement, code 0.
- [ ] La CI détecte un `schemas/` désynchronisé.
