# F10 — Orchestration GitHub Actions

- **Statut** : 🚧 In progress (M1, 2026-11-25) — M3 : ✅ Approved, plan à compléter
- **Milestone** : M1 (exigences et critères `[M1]` : daily sans signaux, deploy, backfill) puis M3 (`[M3]` : étapes signal/paper du daily, weekly-train)
- **Dépend de** : F00, F01, F02, F08 (M1) ; F05, F06, F07 pour les éléments `[M3]`
- **Contrats** : `03-data-contracts.md` §6 (lecture du rapport de run), §7 (`git_sha` du manifest)
- **Principes clés** : P5 (journalisation des réécritures), P6 (frugalité, aucun secret), P7 (rapport même en échec)
- **Référence** : `02-architecture.md` § « Pièges GitHub connus »

## Objectif
Faire tourner le pipeline sans intervention : chaque soir de bourse, ingérer, valider, commiter les données et publier le
dashboard ; à la demande, rattraper un historique ; en M3, produire signaux, portefeuilles fictifs et modèles.

## User stories
- En tant qu'owner, chaque soir de bourse, les données sont commitées et le dashboard public est à jour sans que j'intervienne.
- En tant qu'owner, si une étape échoue, le workflow est rouge, rien de corrompu n'est publié et le rapport de run est téléchargeable.
- En tant qu'owner, je relance un backfill d'un ou plusieurs symboles depuis l'interface Actions.

## Définitions
- **`S`** : dernière séance clôturée, définie par F01.
- **`T0`** : horodatage UTC pris au début du job `pipeline`, transmis aux commandes qui en ont besoin.
- **SHA poussé** : SHA du commit créé et poussé par le job `pipeline`, exposé en *output* du job (vide s'il n'y a pas eu de commit).
- **Régime normal** : run du daily en mode incrémental (F01 R3), sans réécriture d'historique ni relance de la source,
  sur l'univers de `config/universe.yaml` (≈ 20 tickers). Sa durée est celle du workflow complet (`pipeline` + `deploy`)
  affichée par GitHub.

## Workflows

### `daily.yml` `[M1]`, complété en `[M3]`
- Déclencheurs : `schedule: '30 22 * * 1-5'`, `workflow_dispatch`.
- `concurrency: { group: data-writer, cancel-in-progress: false }` au niveau du workflow.
- Job `pipeline` (`contents: write`) : checkout → setup uv (cache) → `th ingest` → `th validate` →
  `[M3]` `th signal` → `th paper` → commit & push (R3, R4) → output `pushed_sha`.
- Job `deploy` (`contents: read`, `pages: write`, `id-token: write`) : `needs: pipeline`, appelle
  `./.github/workflows/deploy-pages.yml` avec `ref: <pushed_sha>`, sous la condition de R9.

### `backfill.yml` `[M1]`
- `workflow_dispatch` avec inputs `symbols` (chaîne, facultative : vide = tout l'univers et le benchmark), `full`
  (booléen, défaut `false`), `start` (chaîne `YYYY-MM-DD`, facultative).
- Même `concurrency` que le daily. → `th ingest [--symbols …] [--full] [--start …]` → `th validate` → commit & push
  (`--kind backfill`) → deploy (mêmes règles que le daily).
- Les inputs sont transmis par `env:` (R14) ; leur validation (symbole inconnu, `--start` sans `--full`, date invalide ou
  future) est celle de F01 R13 : code 2, aucun appel réseau, donc arrêt immédiat selon R7.

### `deploy-pages.yml` (réutilisable) `[M1]`
- Déclencheurs : `workflow_call` (input `ref`), `push` sur `main` touchant les chemins de R10, `workflow_dispatch`.
- `concurrency: { group: pages, cancel-in-progress: false }` — jamais `data-writer` (R2).
- `permissions: { contents: read, pages: write, id-token: write }`.
- Checkout de `ref` (défaut : `github.sha`) → `th export` avec `TH_GIT_SHA` = SHA extrait → `npm ci` →
  `npm run build` avec `TH_DASHBOARD_BASE=/<nom du dépôt>/` (F00 R14, F09 R7) → `npm run check:dist` →
  `actions/upload-pages-artifact` (`dashboard/dist`) → `actions/deploy-pages` (environnement `github-pages`).

### `weekly-train.yml` `[M3]`
- Déclencheurs : `schedule: '0 3 * * 6'` (samedi), `workflow_dispatch` (input `family`, facultatif).
- Même `concurrency` que le daily. `timeout-minutes: 120` sur le job `pipeline` (P6).
- `th train` (sans `family` : chaque famille ML active de `config/strategies.yaml`) → `th backtest random --n 100` →
  `th promote` → commit (`--kind model`, chemins `models/registry/**` et emplacement de la distribution des random
  traders défini par F05 R3) → deploy.

### `ci.yml`
- Créé par F00 (R15–R17). F10 n'y ajoute rien : le test e2e smoke du dashboard appartient à F09 (R8).

## Exigences

### Permissions et concurrence
- **R1** `[M1]` Chaque workflow DOIT déclarer `permissions` au niveau du workflow **et** de chaque job, selon ce tableau
  (aucune autre permission) :

  | Workflow / job | Permissions |
  |---|---|
  | `daily` / `pipeline`, `backfill` / `pipeline`, `weekly-train` / `pipeline` | `contents: write` |
  | job `deploy` appelant `deploy-pages.yml` (dans `daily`, `backfill`, `weekly-train`) | `contents: read`, `pages: write`, `id-token: write` |
  | `deploy-pages` | `contents: read`, `pages: write`, `id-token: write` |
  | niveau workflow de `daily`, `backfill`, `weekly-train` | `contents: read` |

  Le job appelant d'un workflow réutilisable DOIT accorder lui-même les permissions du workflow appelé (elles ne peuvent
  pas dépasser celles de l'appelant).
- **R2** `[M1]` `daily`, `backfill` et `weekly-train` DOIVENT partager le groupe `concurrency` `data-writer` avec
  `cancel-in-progress: false`. `deploy-pages` DOIT utiliser le groupe `pages` avec `cancel-in-progress: false` et NE DOIT
  PAS utiliser `data-writer` (un workflow appelé dans le même groupe que son appelant se bloque ou s'annule).

### Commit et push
- **R3** `[M1]` Le commit DOIT être fait par `github-actions[bot]`
  (`41898282+github-actions[bot]@users.noreply.github.com`), seulement si `git status --porcelain -- <chemins>` n'est
  pas vide (fichiers modifiés **ou non suivis**), en n'ajoutant que ces chemins : `data/` pour `daily` et `backfill`,
  `models/registry/` et le chemin F05 pour `weekly-train`. Il NE DOIT jamais inclure `dashboard/public/data/`.
- **R4** `[M1]` Le push DOIT faire `git pull --rebase` avant, avec 3 tentatives au plus. Il DOIT être exécuté seulement
  si `github.ref == 'refs/heads/main'` ; sur une autre branche, le job s'arrête avant le commit sans échouer.
- **R5** `[M1]` Le message de commit DOIT être produit par `th commit-message --kind {daily|backfill|model} --since T0`
  (sans appel réseau, testé par pytest), qui affiche sur stdout :
  - `daily` : `data: daily update {D}` ; `backfill` : `data: backfill {D}` ; `model` : `model: weekly training {D}` ;
  - suivi de ` (history rewrite: A, B)` QUAND au moins une entrée `ingest` démarrée à `T0` ou après contient un ticker
    avec `history_rewritten: true` (symboles triés, dédoublonnés). C'est la journalisation explicite exigée par P5 (F01 R4).

  `D` = `session_date` des rapports `data/runs/*.json` ayant une entrée `ingest` démarrée à `T0` ou après (la plus
  récente) ; à défaut, `S` calculée à l'exécution. Seules les entrées démarrées à `T0` ou après sont prises en compte,
  pour ne pas reprendre les réécritures d'un run antérieur de la même séance.

### Échecs et rapport
- **R6** `[M1]` QUAND une étape échoue, le workflow DOIT quand même téléverser `data/runs/` comme artefact
  (`if: always()`, `if-no-files-found: ignore`) et finir en échec (notification GitHub standard).
- **R7** `[M1]` Comportement selon les codes de sortie :
  - `th ingest` code **2** (config/arguments) → arrêt immédiat : pas de validate, commit ni deploy ;
  - `th ingest` code **1** (tous les tickers tentés en échec, P7) → `th validate` est exécuté ; s'il sort en 0, le
    rapport est commité et déployé (pour que la page Health montre la panne), puis le job **finit en échec** ;
  - `th ingest` code **0** avec des tickers `failed` (échec partiel) → le workflow reste vert ; l'échec est visible dans
    le rapport et la page Health ;
  - `th validate` code **1** ou **2** (F02 R6) → les étapes suivantes, le commit et le déploiement NE DOIVENT PAS être exécutés.

### Déploiement
- **R8** `[M1]` Le déploiement DOIT publier exactement le SHA poussé : `deploy-pages` fait le checkout de l'input `ref`
  et exporte `TH_GIT_SHA` égal au SHA extrait, de sorte que `manifest.json` porte ce SHA (F08 R11). `GITHUB_SHA`,
  qui désigne le commit déclencheur d'un run `schedule` et non le commit de données, n'est pas utilisé pour cela.
- **R9** `[M1]` Le job `deploy` de `daily`, `backfill` et `weekly-train` DOIT s'exécuter SSI un commit a été poussé
  (`pushed_sha` non vide) **ou** le run est un `workflow_dispatch` sur `main` ; dans ce dernier cas sans commit,
  `ref` = SHA courant de `main`. Un `workflow_dispatch` sur une autre branche ne déploie jamais (R4). Un run sans nouvelle donnée (jour férié, 2e run) ne déploie pas.
- **R10** `[M1]` `deploy-pages` DOIT se déclencher sur un `push` vers `main` touchant `dashboard/**`, `src/**`,
  `config/**`, `data/**`, `models/**`, `pyproject.toml` ou `uv.lock` (les pushes du bot ne déclenchent rien :
  `GITHUB_TOKEN`, d'où l'appel explicite par R9).

### Divers
- **R11** `[M1]` Les actions tierces DOIVENT être épinglées par SHA de commit.
- **R12** `[M1]` Le daily DOIT durer < 15 min en régime normal. Chaque job DOIT déclarer `timeout-minutes` :
  30 pour le job `pipeline` de `daily` et `backfill` (P6), 120 pour celui de `weekly-train` (P6), 15 pour `deploy-pages`.
- **R13** `[M1]` Le README DOIT documenter, dans une section « Mise en service » :
  - le réglage manuel Pages → Source « GitHub Actions » (sans lui, le premier déploiement échoue) ;
  - que le réglage Actions → « Workflow permissions » peut rester sur « Read repository contents » : les écritures sont
    accordées par les clés `permissions` des workflows (R1) ;
  - qu'une protection de `main` ne doit pas empêcher `github-actions[bot]` de pousser ;
  - la relance manuelle (`workflow_dispatch`) du daily, du backfill et de `deploy-pages`, et les limites de R15.
- **R14** `[M1]` Aucune étape `run:` NE DOIT interpoler directement une valeur fournie par l'utilisateur
  (`${{ inputs.* }}`, `${{ github.event.inputs.* }}`) : ces valeurs DOIVENT passer par `env:` et être citées
  (`"$VAR"`) dans le script, pour empêcher l'injection de commandes.
- **R15** `[M1]` Les limites suivantes de GitHub Actions sont acceptées et DOIVENT être documentées (README) :
  - un groupe `concurrency` ne garde qu'**un** run en attente : un 3e run annule celui qui attend (un daily annulé est
    rattrapé par le suivant, F01 R3 ; un backfill annulé est à relancer) ;
  - les runs `schedule` peuvent être retardés ou sautés : `S` (F01) gère le passage de minuit, et le run suivant
    rattrape les séances manquées ;
  - un commit poussé dont le déploiement échoue laisse le site sur l'export précédent jusqu'au prochain déploiement
    (R9) ou à une relance manuelle de `deploy-pages` ;
  - les notifications d'échec d'un run `schedule` vont à la dernière personne ayant modifié le cron.

## Critères d'acceptation

### M1
- [ ] Test sur `.github/workflows/*.yml` (PyYAML) : permissions du tableau R1 au niveau workflow et job, groupes
  `concurrency` de R2, aucune action tierce non épinglée par un SHA de 40 caractères, `timeout-minutes` de R12 sur
  chaque job, aucun `${{ inputs.* }}` ni `${{ github.event.inputs.* }}` dans un `run:`. (R1, R2, R11, R12, R14)
- [ ] `th commit-message` : sans réécriture → `data: daily update 2026-11-23` ; avec réécritures AAPL et MSFT dans une
  entrée postérieure à `T0` → `… (history rewrite: AAPL, MSFT)` ; réécriture dans une entrée antérieure à `T0` ignorée ;
  `--kind backfill` et `--kind model` ; aucun rapport récent → `D = S`. (R5)
- [ ] Un nouveau fichier non suivi sous `data/` (ex. `data/runs/{S}.json`) est commité ; aucun diff → aucun commit,
  `pushed_sha` vide, pas de deploy. (R3, R9)
- [ ] Un `workflow_dispatch` du daily sur `main` réussit de bout en bout ; un `workflow_dispatch` sur une autre branche
  s'arrête avant le commit, sans échec. (R4, R9)
- [ ] Deux runs `data-writer` lancés simultanément s'exécutent l'un après l'autre sans conflit ; le deploy appelé ne se
  bloque pas. (R2)
- [ ] Fixture de prix corrompue sur `main` puis daily : job rouge, artefact `data/runs/` présent, aucun commit, aucun
  deploy. (R6, R7)
- [ ] Après un daily, `https://<owner>.github.io/TradingHelper/data/manifest.json` contient `data_as_of = S` et
  `git_sha` = SHA du commit `data:` poussé. (R8)
- [ ] Les 5 premiers daily réels en régime normal durent chacun < 15 min (durées relevées dans la vérification). (R12)
- [ ] `workflow_dispatch` du backfill avec `start` et sans `full` → job en échec sur le code 2 de `th ingest`, aucun
  commit ; avec `symbols: AAPL`, `full: true` → commit `data: backfill … (history rewrite: AAPL)` et deploy. (R5, R7, R14)
- [ ] Les daily et deploy réussissent avec le réglage « Read repository contents » ; le README contient la section
  « Mise en service » avec les points de R13 et R15 (grep). (R1, R13, R15)

### M3
- [ ] Un `workflow_dispatch` de `weekly-train` commite le registre et déploie. (Workflows)

## Hors périmètre
- Test e2e smoke du dashboard : porté par F09 (R8), y compris son ajout à `ci.yml`.
- Une section `run-report` du rapport de run : chaque commande écrit déjà sa section, avec ses durées (contrat §6).

## Dépendances introduites
Aucune (PyYAML, déjà présent, sert au test des workflows).

## Pré-requis sur d'autres specs
- **F08 R11** : ordre de résolution de `git_sha` modifié (`TH_GIT_SHA` > `git rev-parse HEAD` > `GITHUB_SHA` > `null`) ;
  l'implémentation de ce changement est une tâche de F10.

## Décisions (validées le 2026-11-25)
- **Q1** Exigences et critères étiquetés `[M1]`/`[M3]` (comme F08). Le backfill passe en M1 (il ne dépend que de F01).
- **Q2** Pas de commande `th run-report` : chaque commande écrit sa section du rapport (contrat §6).
- **Q3** Ingestion entièrement en échec (code 1) : le rapport est commité et déployé, puis le job échoue (P7) (R7).
- **Q4** Échec partiel (code 0 avec tickers `failed`) : workflow vert, échec visible dans Health (R7).
- **Q5** Pas de déploiement sans nouveau commit, sauf `workflow_dispatch` (R9).
- **Q6** `git_sha` : checkout du SHA poussé + variable `TH_GIT_SHA`, et modification de F08 R11 (R8).
- **Q7** Logique testable en Python : `th commit-message` ; les workflows ne contiennent que de l'enchaînement (R5).
- **Q8** Le test e2e Playwright reste à F09 (R8) ; F10 ne modifie pas `ci.yml`.
- **Q9** `deploy-pages` se déclenche sur les pushes humains touchant dashboard, code, config, données ou modèles (R10).
- **Q10** Weekly : sans input `family`, toutes les familles ML actives ; commit de `models/registry/**` et du fichier de
  distribution des random traders (emplacement fixé par F05 R3).

- **Q11** Inputs utilisateur passés par `env:` ; validation des arguments du backfill déléguée à F01 R13 (R14).
- **Q12** Régime normal défini (Définitions) ; `timeout-minutes` 30 / 120 / 15 alignés sur P6 (R12).
- **Q13** Le réglage dépôt « Read and write permissions » n'est plus exigé : les clés `permissions` suffisent et
  gardent le défaut en lecture seule (R1, R13).
- **Q14** File d'attente `concurrency`, retards du cron, déploiement en échec et notifications : limites acceptées et
  documentées, sans mécanisme supplémentaire (R15).

## Questions ouvertes
Aucune.
