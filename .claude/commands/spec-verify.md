---
description: Vérifier les critères d'acceptation d'une feature
argument-hint: <Fxx>
---
Vérifie la feature `$ARGUMENTS`.

1. Toutes les tâches de `tasks.md` sont-elles cochées ? Sinon liste celles qui manquent et arrête-toi.
2. Pour **chaque** critère d'acceptation de `spec.md` : exécute le test ou la commande qui le prouve et note la preuve (nom du test, sortie).
3. Pour chaque exigence `Rn` : identifie le(s) test(s) qui la couvrent ; signale toute exigence non couverte.
4. Lance la suite complète (lint, mypy, tests, build dashboard).
5. Coche les critères prouvés dans `spec.md`, passe le statut à 🔍 Verifying (ou ✔️ Done si tout est prouvé et que je valide), mets à jour `specs/roadmap.md`.
6. Rapport final : tableau critère → preuve → OK/KO.
