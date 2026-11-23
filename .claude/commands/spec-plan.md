---
description: Produire le plan technique d'une feature (aucun code)
argument-hint: <Fxx>
---
Produis le plan technique de la feature `$ARGUMENTS`.

1. Vérifie que `specs/features/$ARGUMENTS*/spec.md` est au statut ✅ Approved. Sinon, arrête-toi et dis-le.
2. Lis `CLAUDE.md`, la constitution, l'architecture, les contrats, la spec, et les specs/plans des dépendances. Explore le code existant concerné.
3. Écris `plan.md` dans le dossier de la feature à partir de `specs/_templates/plan.md` :
   - chaque exigence `Rn` apparaît dans la table de traçabilité avec au moins un test prévu ;
   - la table « Vérification constitution » couvre tous les principes pertinents ;
   - toute nouvelle dépendance est justifiée ;
   - toute décision d'architecture non triviale → propose un ADR.
4. **N'écris aucun code de production ni de test.**
5. Termine en listant les points que je dois valider, puis passe le statut à 🧭 Planned seulement après mon accord.
