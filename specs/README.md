# Specs — mode d'emploi SDD avec Claude Code

## Organisation
```
specs/
├── 00-constitution.md      # principes non négociables
├── 01-vision.md            # produit, périmètre
├── 02-architecture.md      # stack, arborescence, abstractions
├── 03-data-contracts.md    # formats JSON
├── roadmap.md              # milestones, ordre, statuts
├── adr/                    # décisions d'architecture (NNNN-titre.md)
├── _templates/             # spec.md, plan.md, tasks.md, adr.md
└── features/
    └── Fxx-nom/
        ├── spec.md         # QUOI / POURQUOI  (humain)
        ├── plan.md         # COMMENT          (généré par /spec-plan, relu par l'humain)
        └── tasks.md        # ÉTAPES           (généré par /spec-tasks, coché pendant l'implémentation)
```

## Cycle de vie d'une feature
| Statut | Signification | Qui |
|---|---|---|
| 📝 Draft | Spec en cours d'écriture | humain (+ Claude pour challenger) |
| ✅ Approved | Spec figée, prête à planifier | humain |
| 🧭 Planned | `plan.md` + `tasks.md` relus et acceptés | Claude propose, humain valide |
| 🚧 In progress | Tâches en cours | Claude |
| 🔍 Verifying | Toutes tâches cochées, vérif des critères | Claude |
| ✔️ Done | Critères d'acceptation prouvés, mergé | humain |

## Commandes Claude Code (`.claude/commands/`)
| Commande | Effet |
|---|---|
| `/spec-new <nom>` | Crée `features/Fxx-nom/spec.md` depuis le template et pose les questions de clarification. |
| `/spec-review Fxx` | Critique la spec : ambiguïtés, exigences non testables, conflits avec la constitution. |
| `/spec-plan Fxx` | Produit `plan.md`. **Aucun code.** |
| `/spec-tasks Fxx` | Découpe le plan en `tasks.md`. |
| `/spec-implement Fxx [Tn]` | Implémente la prochaine tâche (ou `Tn`) en TDD, coche la tâche, commit. |
| `/spec-verify Fxx` | Vérifie chaque critère d'acceptation avec preuve et met à jour le statut. |

## Conseils pratiques
- Une feature = une branche `feat/Fxx-nom` = une PR. Démarrer une **nouvelle session Claude** par feature pour garder un contexte propre ; les specs suffisent comme mémoire.
- Relire `plan.md` attentivement : c'est le meilleur moment pour corriger la trajectoire (10× moins cher qu'après le code).
- Garder les exigences **testables** : chaque `Rn` doit pouvoir être reliée à au moins un test.
- Les sections « Questions ouvertes » doivent être vides avant de passer en ✅ Approved.
