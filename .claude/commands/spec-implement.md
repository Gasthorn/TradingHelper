---
description: Implémenter la prochaine tâche d'une feature en TDD
argument-hint: <Fxx> [Tn]
---
Implémente une tâche de la feature (arguments : `$ARGUMENTS` — si aucune tâche n'est précisée, prends la première non cochée de `tasks.md`).

1. Relis `CLAUDE.md`, la spec, le plan et `tasks.md` de la feature. Passe le statut à 🚧 In progress si besoin.
2. Écris d'abord les tests de la tâche et vérifie qu'ils échouent.
3. Implémente le minimum pour les faire passer, en respectant le plan et la constitution.
4. Lance `uv run ruff check . && uv run ruff format . && uv run mypy --strict src/ && uv run pytest` (et `npm run build`/`npm test` dans `dashboard/` si concerné). Tout doit passer.
5. Coche la tâche dans `tasks.md`.
6. Commit : `feat(Fxx): Tn <résumé> (Rn, …)`.
7. Si la spec ou le plan s'avère faux ou incomplet : **arrête-toi** et propose la modification au lieu d'improviser.

Une seule tâche par invocation, sauf si je demande explicitement d'enchaîner.
