# Plan — F10 Orchestration GitHub Actions

> Généré par `/spec-plan`. À relire et valider avant `/spec-tasks`.
> **Portée** : ce plan détaille les exigences et workflows `[M1]` (`daily` sans signaux, `backfill`, `deploy-pages`).
> Les éléments `[M3]` (étapes `th signal` / `th paper` du daily, `weekly-train.yml`) ne sont qu'esquissés : les commandes
> `th signal`, `th paper`, `th train`, `th backtest`, `th promote` n'existent pas encore (F05–F07). Le plan sera complété
> avant le découpage des tâches M3.

## Résumé de l'approche
F10 n'ajoute presque pas de logique métier : les workflows **enchaînent** des commandes déjà testées. Tout ce qui
demande une décision est sorti du YAML pour être testable hors de GitHub (Q7) :

1. **`th commit-message`** (nouveau) : une fonction **pure** `build_commit_message` dans
   `src/tradinghelper/orchestration/commit_message.py` construit le message à partir des rapports de run ; la commande
   lit `data/runs/*.json` et affiche le message (R5).
2. **`scripts/ci/commit-and-push.sh`** (nouveau, bash) : un seul script partagé par `daily`, `backfill` et (M3)
   `weekly-train` : identité du bot, test `git status --porcelain`, `git add` limité aux chemins donnés, commit,
   `git pull --rebase` + push avec 3 tentatives, écriture de `pushed_sha` / `head_sha` dans `$GITHUB_OUTPUT` (R3, R4).
   Testé par pytest contre un dépôt distant local (`git init --bare`), sans réseau.
3. **Workflows** `.github/workflows/daily.yml`, `backfill.yml`, `deploy-pages.yml` : enchaînement, permissions,
   concurrence, conditions. Leur structure est vérifiée par un test pytest qui lit le YAML (PyYAML, déjà présent),
   sur le modèle des tests existants de `ci.yml`.
4. **F08 R11** : `resolve_git_sha` passe à l'ordre `TH_GIT_SHA` > `git rev-parse HEAD` > `GITHUB_SHA` > `None` (R8).
5. **Documentation** : section README « Mise en service » (R13, R15), `CLAUDE.md`, arborescence de l'architecture.

**Trois jobs dans `daily` et `backfill`, pour que l'échec arrive après le déploiement (R7).** Une ingestion entièrement
en échec (code 1) doit être commitée et déployée **puis** rendre le run rouge. Faire échouer le job `pipeline` empêcherait
le job `deploy` de s'exécuter normalement. Le daily a donc trois jobs :

```
pipeline ──(pushed_sha, head_sha, ingest_exit_code)──► deploy (appelle deploy-pages.yml) ──► conclude
```

- `pipeline` traduit le code de `th ingest` : **2** → échec immédiat ; **1** → on continue, code mémorisé en output ;
  **0** → on continue. `th validate` en échec arrête le job (comportement par défaut de `bash -e`).
- `deploy` s'exécute si `pipeline` a réussi et R9 est vrai.
- `conclude` (`if: always()`) échoue si `pipeline` ou `deploy` a échoué **ou** si `ingest_exit_code == 1`. C'est le
  seul endroit où la règle « rouge mais publié » est écrite.

**Déploiement du SHA poussé (R8).** `deploy-pages.yml` reçoit l'input `ref`, fait le checkout de ce SHA et passe
`TH_GIT_SHA=$(git rev-parse HEAD)` à `th export`. `GITHUB_SHA` n'est plus prioritaire dans `resolve_git_sha`.

## Vérification constitution
| Principe | Impact | Comment il est respecté |
|---|---|---|
| P1 | Aucun | F10 n'ajoute aucune logique de décision. L'ordre des étapes (ingest → validate → `[M3]` signal → paper) ne fait consommer à une stratégie que des données validées et clôturées (F01 R7). |
| P2 | Aucun | Pas de logique de décision dans les workflows. En M3, `th signal` et `th paper` appellent le moteur unique (F07). |
| P3 | Aucun en M1 | En M3, le weekly enchaîne `th backtest random` puis `th promote`, qui applique les règles de F06 R4. |
| P4 | Moyen | Actions épinglées par SHA (R11), `uv sync --locked`, `npm ci`. Le manifest publié porte le SHA exact des données déployées (R8). Le message de commit est déterministe à rapports égaux. |
| P5 | **Fort** | Les réécritures d'historique sont journalisées dans le message de commit (R5, F01 R4). Seuls `data/` (et en M3 `models/registry/`) sont commités, jamais `dashboard/public/data/` (R3). Rien n'est commité si `th validate` détecte une violation (R7). Aucune modification manuelle de `data/raw/`. |
| P6 | **Fort** | `ubuntu-latest` uniquement, aucun secret (seul `GITHUB_TOKEN`), `timeout-minutes` 30 / 15 / 120 (R12). Cache uv et npm. Pas de déploiement les jours sans nouvelle donnée (R9). |
| P7 | **Fort** | Échec partiel → run vert, visible dans Health. Échec total de l'ingestion → rapport commité et déployé, puis run rouge (R7). Artefact `data/runs/` téléversé dans tous les cas (R6). Push retenté 3 fois (R4). Écritures déjà atomiques (F01, F02). |
| P8 | Faible | Le bandeau est vérifié dans le build publié par `npm run check:dist` (étape de `deploy-pages`). |
| P9 | Moyen | `orchestration/commit_message.py` pur, typé, `mypy --strict`. Workflows et script testés par pytest (sans réseau). |

## Fichiers
| Fichier | Action | Rôle |
|---|---|---|
| `src/tradinghelper/orchestration/__init__.py` | créer | Paquet (vide). |
| `src/tradinghelper/orchestration/commit_message.py` | créer | `CommitKind`, `build_commit_message` (pur) (R5). |
| `src/tradinghelper/data/storage.py` | modifier | `read_run_reports(runs_dir)` : lit et valide tous les `data/runs/*.json` (erreur `RunReportError` listée). Mutualisé avec la lecture de l'export si c'est simple, sans changer le comportement de F08. |
| `src/tradinghelper/cli.py` | modifier | Commande `commit-message` (sans config, ajoutée à `CONFIG_EXEMPT_COMMANDS`) ; codes 0/1/2. |
| `src/tradinghelper/export/dashboard.py` | modifier | `resolve_git_sha` : `TH_GIT_SHA` > `git rev-parse HEAD` > `GITHUB_SHA` > `None` (F08 R11, R8). |
| `scripts/ci/commit-and-push.sh` | créer | Commit et push partagés (R3, R4) ; outputs `pushed_sha`, `head_sha`. |
| `.github/workflows/daily.yml` | créer | Jobs `pipeline`, `deploy`, `conclude` (R1–R7, R9, R11, R12). |
| `.github/workflows/backfill.yml` | créer | Mêmes jobs, inputs passés par `env:` (R14). |
| `.github/workflows/deploy-pages.yml` | créer | Workflow réutilisable : export, build, publication (R1, R2, R8, R10–R12). |
| `.gitattributes` | modifier | `*.sh text eol=lf` (un script bash en CRLF échoue sous Linux). |
| `tests/orchestration/test_commit_message.py` | créer | Fonction pure (R5). |
| `tests/test_cli_commit_message.py` | créer | Commande : lecture des rapports, `--since`, codes de sortie (R5). |
| `tests/test_commit_and_push.py` | créer | Script contre un dépôt distant local (R3, R4). |
| `tests/test_workflows.py` | créer | Structure des trois workflows (R1, R2, R4, R6, R7, R9–R12, R14). |
| `tests/export/test_dashboard.py` | modifier | Nouvel ordre de résolution de `git_sha` (R8). |
| `tests/test_repo_hygiene.py` | modifier | README : section « Mise en service », plus d'exigence « Read and write permissions » (R13, R15) ; `.sh` en LF ; `commit_message.py` pur. |
| `README.md` | modifier | Section « Mise en service » (R13, R15) ; commande `th commit-message` ; retrait de « active après F10 » et du réglage « Read and write ». |
| `CLAUDE.md` | modifier | `orchestration/commit_message.py` parmi les modules purs ; commande `th commit-message`. |
| `specs/02-architecture.md` | modifier | Arborescence : `orchestration/`, `scripts/ci/`. |
| `.github/workflows/weekly-train.yml` | créer **(M3)** | Esquisse ci-dessous. |

## Interfaces / signatures
```python
# src/tradinghelper/orchestration/commit_message.py   (pur)
CommitKind = Literal["daily", "backfill", "model"]

PREFIX: Final[dict[CommitKind, str]] = {
    "daily": "data: daily update",
    "backfill": "data: backfill",
    "model": "model: weekly training",
}

def build_commit_message(
    kind: CommitKind,
    reports: Sequence[RunReport],
    *,
    since: datetime,          # T0, UTC
    fallback_session: date,   # S calculée à l'exécution
) -> str: ...
    # Entrées retenues : sections `ingest` dont started_at >= since.
    # D = session_date du rapport contenant l'entrée retenue la plus récente ; sinon fallback_session.
    # Suffixe " (history rewrite: A, B)" si au moins un ticker retenu a history_rewritten=True
    # (symboles dédoublonnés, triés).
```

```python
# src/tradinghelper/data/storage.py   (ajout)
def read_run_reports(runs_dir: Path) -> list[RunReport]: ...
    # Tous les `YYYY-MM-DD.json` de runs_dir, validés par RunReport ; dossier absent → [].
    # Fichier illisible ou hors contrat → RunReportError (le premier rencontré, ordre des noms).
```

```python
# src/tradinghelper/cli.py   (ajout)
@app.command("commit-message")
def commit_message(
    kind: Annotated[CommitKind, typer.Option("--kind")],
    since: Annotated[datetime, typer.Option("--since", help="T0, UTC ISO-8601")],
) -> None: ...
    # Lit data_dir()/runs ; S = NyseCalendar().last_closed_session(_now()).
    # stdout : le message, une seule ligne. Codes : 0 ; 1 rapport invalide (stderr) ;
    # 2 argument invalide (kind inconnu, since sans fuseau ou mal formé).
```

```python
# src/tradinghelper/export/dashboard.py   (modification)
def resolve_git_sha(environ: Mapping[str, str], repo_root: Path) -> str | None: ...
    # TH_GIT_SHA valide > `git rev-parse HEAD` > GITHUB_SHA valide > None
```

```bash
# scripts/ci/commit-and-push.sh   (contrat)
# Usage : commit-and-push.sh "<message>" <chemin> [<chemin>...]
# - identité : github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>
# - si `git status --porcelain -- <chemins>` est vide : pushed_sha= (vide), sortie 0
# - sinon : git add -- <chemins> ; git commit -m "<message>"
#   puis jusqu'à 3 fois : git pull --rebase origin <branche> && git push origin HEAD:<branche>
#   (attentes 5 s puis 10 s entre tentatives, variable TH_PUSH_SLEEP pour les tests) ; échec → code 1
# - écrit pushed_sha=<sha|vide> et head_sha=<HEAD final> dans $GITHUB_OUTPUT (ou stdout hors CI)
```

### Squelette de `daily.yml` (M1)
```yaml
on:
  schedule: [{ cron: '30 22 * * 1-5' }]
  workflow_dispatch:
permissions: { contents: read }
concurrency: { group: data-writer, cancel-in-progress: false }
jobs:
  pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions: { contents: write }
    outputs: { pushed_sha, head_sha, ingest_exit_code }
    steps:
      - checkout (SHA épinglé)
      - setup-uv (cache) ; uv sync --locked
      - id: t0      → echo "value=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_OUTPUT"
      - id: ingest  → set +e ; uv run th ingest ; code=$? ; echo "exit_code=$code" >> "$GITHUB_OUTPUT"
                      ; [ "$code" -eq 1 ] || exit "$code"          # 0 et 1 continuent, 2 arrête
      - uv run th validate                                          # 1 ou 2 → arrêt (R7)
      # [M3] uv run th signal ; uv run th paper
      - id: commit (if: github.ref == 'refs/heads/main')
            → MSG=$(uv run th commit-message --kind daily --since "$T0")
              bash scripts/ci/commit-and-push.sh "$MSG" data/
      - upload-artifact data/runs/ (if: always(), if-no-files-found: ignore, retention 30 j)
  deploy:
    needs: pipeline
    if: needs.pipeline.outputs.pushed_sha != '' ||
        (github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main')
    permissions: { contents: read, pages: write, id-token: write }
    uses: ./.github/workflows/deploy-pages.yml
    with: { ref: <pushed_sha || head_sha> }
  conclude:
    needs: [pipeline, deploy]
    if: always()
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions: {}
    steps: échec si pipeline.result == 'failure' ou deploy.result == 'failure'
           ou ingest_exit_code == '1' (message explicite)
```

`backfill.yml` reprend ces jobs ; l'étape d'ingestion construit ses arguments depuis `env:`
(`TH_IN_SYMBOLS: ${{ inputs.symbols }}`, etc.) avec un tableau bash (`args+=(--symbols "$TH_IN_SYMBOLS")`), puis
`--kind backfill`.

### Squelette de `deploy-pages.yml`
```yaml
on:
  workflow_call: { inputs: { ref: { type: string, required: false, default: '' } } }
  push: { branches: [main], paths: [dashboard/**, src/**, config/**, data/**, models/**, pyproject.toml, uv.lock] }
  workflow_dispatch:
permissions: { contents: read, pages: write, id-token: write }
concurrency: { group: pages, cancel-in-progress: false }
jobs:
  build:   # timeout 15 ; checkout ref (|| github.sha) ; setup-uv ; uv sync --locked
           # TH_GIT_SHA=$(git rev-parse HEAD) uv run th export
           # setup-node (.nvmrc, cache npm) ; npm ci
           # TH_DASHBOARD_BASE=/${{ github.event.repository.name }}/ npm run build ; npm run check:dist
           # upload-pages-artifact (dashboard/dist)
  deploy:  # timeout 15 ; environment github-pages ; deploy-pages
```

### Esquisse M3 (non détaillée)
- `daily.yml` : étapes `uv run th signal` et `uv run th paper` entre `validate` et `commit`.
- `weekly-train.yml` : mêmes trois jobs ; `pipeline` (timeout 120) enchaîne `th train [--family "$TH_IN_FAMILY"]`,
  `th backtest random --n 100`, `th promote`, puis `commit-and-push.sh` avec `--kind model` et les chemins
  `models/registry/` + emplacement F05 R3.

## Traçabilité exigences → design → tests
| Exigence | Élément de design | Test(s) prévu(s) |
|---|---|---|
| R1 | Clés `permissions` workflow + job ; job `deploy` appelant avec `pages`/`id-token` | `tests/test_workflows.py::test_workflow_level_permissions[daily\|backfill\|deploy-pages]`, `::test_job_permissions_match_table`, `::test_caller_job_grants_pages_permissions` ; vérification réelle : runs réussis avec le réglage « Read repository contents » |
| R2 | `concurrency` `data-writer` / `pages` | `test_workflows.py::test_data_writers_share_group[daily\|backfill]`, `::test_deploy_pages_uses_own_group` ; vérification réelle : deux `workflow_dispatch` simultanés |
| R3 | `commit-and-push.sh` : identité du bot, `git status --porcelain`, `git add` limité | `tests/test_commit_and_push.py::test_untracked_file_is_committed`, `::test_no_change_no_commit_empty_pushed_sha`, `::test_only_given_paths_are_committed`, `::test_author_is_github_actions_bot` ; `test_workflows.py::test_commit_paths_exclude_dashboard_data` |
| R4 | Boucle `pull --rebase` + push (3 tentatives) ; garde `github.ref == 'refs/heads/main'` | `test_commit_and_push.py::test_rebases_over_concurrent_push`, `::test_fails_after_three_attempts` (`TH_PUSH_SLEEP=0`), `::test_outputs_written_to_github_output` ; `test_workflows.py::test_commit_step_only_on_main` |
| R5 | `build_commit_message`, `th commit-message`, `read_run_reports` | `tests/orchestration/test_commit_message.py::test_daily_without_rewrite`, `::test_rewrite_symbols_sorted_deduplicated`, `::test_entries_before_since_ignored`, `::test_backfill_and_model_prefixes`, `::test_fallback_session_without_recent_entry`, `::test_session_of_most_recent_entry` ; `tests/test_cli_commit_message.py::test_prints_message_from_reports`, `::test_no_runs_dir_uses_current_session`, `::test_invalid_report_exits_1`, `::test_invalid_since_exits_2`, `::test_runs_without_config` |
| R6 | Étape `upload-artifact` `if: always()` | `test_workflows.py::test_report_artifact_always_uploaded[daily\|backfill]` |
| R7 | Traduction du code d'ingestion, `validate` bloquant, job `conclude` | `test_workflows.py::test_ingest_exit_2_stops_and_1_continues` (texte du script de l'étape), `::test_validate_step_not_continue_on_error`, `::test_conclude_fails_on_ingest_exit_1`, `::test_conclude_runs_always` ; vérification réelle : fixture corrompue sur `main` → rouge, artefact, ni commit ni deploy |
| R8 | Input `ref`, checkout, `TH_GIT_SHA` ; `resolve_git_sha` réordonné | `tests/export/test_dashboard.py::test_git_sha_th_git_sha_first`, `::test_git_sha_repo_head_before_github_sha`, `::test_git_sha_github_sha_fallback_outside_git`, `::test_git_sha_invalid_env_ignored` (adapté) ; `test_workflows.py::test_deploy_checks_out_ref_and_sets_th_git_sha` ; vérification réelle : `manifest.json` publié |
| R9 | Condition du job `deploy`, `ref` = `pushed_sha` ou `head_sha` | `test_workflows.py::test_deploy_condition[daily\|backfill]` |
| R10 | `on.push.paths` de `deploy-pages` | `test_workflows.py::test_deploy_pages_push_paths` |
| R11 | `uses:` épinglés | `test_workflows.py::test_actions_pinned_by_sha[daily\|backfill\|deploy-pages]` (même règle que `test_ci_actions_pinned_by_sha`) |
| R12 | `timeout-minutes` par job | `test_workflows.py::test_job_timeouts` ; durée < 15 min : relevé des 5 premiers daily à la vérification |
| R13 | Section README « Mise en service » | `tests/test_repo_hygiene.py::test_readme_has_mise_en_service_section` (Pages « GitHub Actions », « Read repository contents », protection de `main`, relance manuelle) |
| R14 | Inputs par `env:`, citations `"$VAR"` | `test_workflows.py::test_no_user_input_interpolated_in_run` (aucun `${{ inputs.` ni `${{ github.event.inputs.` dans un `run:`) ; vérification réelle : backfill `start` sans `full` → code 2 |
| R15 | Limites documentées dans le README | `test_repo_hygiene.py::test_readme_documents_actions_limits` (file d'attente `concurrency`, retards du cron, déploiement en échec, notifications) |

## Dépendances ajoutées
| Paquet | Version | Justification |
|---|---|---|
| — | — | Aucune dépendance Python ou npm. PyYAML (déjà présent) sert aux tests des workflows. |
| Actions GitHub | épinglées par SHA à l'implémentation | `actions/checkout`, `astral-sh/setup-uv`, `actions/setup-node` (déjà utilisées par `ci.yml`, mêmes SHA) ; nouvelles : `actions/upload-artifact`, `actions/upload-pages-artifact`, `actions/deploy-pages` (officielles GitHub, aucune alternative pour Pages via Actions). |

## Risques & mitigations
- **Outputs d'un job en échec / conditions `needs`** : les expressions `if:` des jobs sont faciles à rater (un job
  sauté rend `needs.*.result == 'skipped'`). → La règle d'échec est centralisée dans `conclude`, testée par
  `test_workflows.py`, puis vérifiée par des runs réels : succès, jour sans données, fixture corrompue. Le chemin
  « ingestion entièrement en échec » (code 1) ne peut pas être provoqué en réel sans panne de yfinance : il est couvert
  par les tests de structure (`conclude`, script de l'étape d'ingestion).
- **Workflows non testables localement de bout en bout** (`act` ne gère ni OIDC ni Pages). → Tests de structure
  en pytest, puis vérification réelle par `workflow_dispatch` sur `main` après la fusion de la PR (critères de la spec).
- **Script bash testé sous Windows** : les tests de `commit-and-push.sh` exigent `bash` (Git Bash en local, natif en
  CI) ; `pytest.mark.skipif(shutil.which("bash") is None)`. Fins de ligne forcées en LF par `.gitattributes`.
- **2e run du daily pour la même séance** : `th validate` ajoute une entrée au rapport existant (F02 R7), ce qui crée
  un commit `data: daily update S` et un déploiement. Comportement accepté (relance manuelle rare), documenté.
- **Rebase en conflit** : seul un humain qui modifie `data/` en parallèle peut le provoquer (les écrivains automatiques
  sont sérialisés par `data-writer`). Le script abandonne le rebase (`git rebase --abort`), échoue après 3 tentatives
  et l'artefact garde le rapport ; le run suivant ré-ingère (F01 idempotent).
- **Premier déploiement** : échoue tant que Pages n'est pas réglé sur « GitHub Actions » → section « Mise en service »
  (R13) ; le réglage est fait par l'owner avant la vérification.
- **Changement de F08 R11 sur une feature livrée** : risque de régression sur `git_sha`. → Tests existants adaptés
  plus nouveaux cas ; le critère F08 ajouté est coché à la vérification de F10.
- **SHA des nouvelles actions** : récupérés à l'implémentation depuis les releases officielles (`gh api`), commentaire
  `# vX.Y.Z` comme dans `ci.yml`.

## Questions pour l'humain
1. **Commit et push en bash** (`scripts/ci/commit-and-push.sh`, testé par pytest contre un dépôt local) plutôt qu'une
   commande Python `th publish` : d'accord ? Le bash est plus court et plus lisible dans un workflow ; le Python serait
   testable sans `bash` sous Windows.
2. **Job `conclude`** pour faire échouer le run après le déploiement (R7) : d'accord avec cette structure en 3 jobs ?
3. **Nom du paquet** `tradinghelper.orchestration` pour `commit_message.py` (absent de l'arborescence actuelle) : d'accord,
   ou préférence pour un autre emplacement (ex. `tradinghelper/ops/`) ?
4. **`th commit-message` sans configuration** (comme `th schemas`) : il n'a besoin que de `data/runs/` et du calendrier.
   D'accord ?
5. **Rétention de l'artefact** `data/runs/` : 30 jours proposés.
6. **ADR** : aucune décision ne me semble mériter un ADR (les choix structurants — appel explicite de `deploy-pages`,
   groupes de concurrence, `TH_GIT_SHA` — sont déjà dans la spec et l'architecture). À confirmer.
