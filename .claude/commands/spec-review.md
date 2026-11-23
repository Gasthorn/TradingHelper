---
description: Critiquer une spec avant approbation
argument-hint: <Fxx>
---
Relis de façon critique la spec `specs/features/$ARGUMENTS*/spec.md`.

Lis d'abord `specs/00-constitution.md`, `specs/02-architecture.md`, `specs/03-data-contracts.md` et les specs dont elle dépend.

Produis un rapport (sans modifier de fichier) :
- Exigences ambiguës ou non testables (citer `Rn`, proposer une reformulation).
- Conflits avec la constitution ou d'autres specs.
- Cas limites oubliés (jours fériés, données manquantes, premier run, reprise après échec…).
- Critères d'acceptation manquants pour certaines exigences.
- Questions ouvertes à trancher avant ✅ Approved.

Termine en me demandant quelles corrections appliquer.
