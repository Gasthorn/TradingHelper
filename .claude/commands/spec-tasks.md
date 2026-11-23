---
description: Découper le plan d'une feature en tâches
argument-hint: <Fxx>
---
À partir de `specs/features/$ARGUMENTS*/spec.md` et `plan.md`, écris `tasks.md` (template `specs/_templates/tasks.md`).

Règles :
- Tâches petites (≤ ~1 h), ordonnées, chacune liée à ≥ 1 exigence `Rn`.
- Chaque tâche indique les tests à écrire en premier, les fichiers touchés, et une condition « fini quand » vérifiable.
- Toutes les exigences de la spec sont couvertes par au moins une tâche (vérifie et affiche la couverture).
- Dernière tâche : vérification des critères d'acceptation.
N'écris aucun code.
