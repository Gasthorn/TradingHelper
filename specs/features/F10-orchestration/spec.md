# F10 — Orchestration GitHub Actions

- **Statut** : 📝 Draft
- **Milestone** : M1 (daily + deploy) puis M3 (weekly-train)
- **Dépend de** : F00, F01, F02, F08 ; F06/F07 pour les étapes correspondantes
- **Référence** : `02-architecture.md` § « Pièges GitHub connus »

## Workflows

### `daily.yml`
- Déclencheurs : `schedule: '30 22 * * 1-5'`, `workflow_dispatch`.
- `concurrency: { group: data-writer, cancel-in-progress: false }`.
- Job `pipeline` : checkout → setup uv (cache) → `th ingest` → `th validate` → `th signal` → `th paper` → `th run-report` → commit & push si diff (`data: daily update YYYY-MM-DD`).
- Job `deploy` : `needs: pipeline`, appelle `deploy-pages.yml` (`uses: ./.github/workflows/deploy-pages.yml`).

### `weekly-train.yml`
- Déclencheurs : `schedule: '0 3 * * 6'` (samedi), `workflow_dispatch` (input `family`).
- Même `concurrency`. `timeout-minutes: 120`.
- `th train` → `th backtest random --n 100` → `th promote` → commit (`model: weekly training`) → deploy.

### `backfill.yml`
- `workflow_dispatch` avec inputs `symbols`, `start`, `full`. → `th ingest …` → validate → commit → deploy.

### `deploy-pages.yml` (réutilisable)
- Déclencheurs : `workflow_call`, `push` sur `main` touchant `dashboard/**`, `workflow_dispatch`.
- `permissions: { pages: write, id-token: write, contents: read }`.
- Checkout (ref `main` à jour) → `th export` → `npm ci && npm run build` → `actions/upload-pages-artifact` → `actions/deploy-pages`.

### `ci.yml`
- Voir F00. Ajouter : vérification `schemas/` à jour, test e2e smoke du dashboard.

## Exigences
- **R1** Chaque workflow DOIT déclarer des `permissions` minimales explicites.
- **R2** Le commit DOIT être fait par `github-actions[bot]` et seulement s'il y a un diff (`git diff --quiet || …`).
- **R3** Le push DOIT faire `git pull --rebase` avant, avec 3 tentatives.
- **R4** QUAND une étape échoue, le workflow DOIT quand même téléverser `data/runs/{date}.json` comme artefact et échouer visiblement (notification GitHub standard).
- **R5** Les actions tierces DOIVENT être épinglées par SHA de commit.
- **R6** Le daily DOIT durer < 15 min en régime normal.
- **R7** Le dépôt DOIT documenter dans le README les réglages manuels : Pages → Source « GitHub Actions » ; Actions → « Read and write permissions ».

## Critères d'acceptation
- [ ] `act` ou un run `workflow_dispatch` réussit de bout en bout sur une branche de test.
- [ ] Deux runs lancés simultanément s'exécutent l'un après l'autre sans conflit.
- [ ] Après un daily, le dashboard publié affiche la nouvelle `data_as_of`.
