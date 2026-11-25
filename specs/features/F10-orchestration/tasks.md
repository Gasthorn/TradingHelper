# Tâches — F10 Orchestration GitHub Actions (M1)

> Généré par `/spec-tasks`. Chaque tâche est petite (≤ ~1 h), testable, et référence ses exigences.
> Ordre = ordre d'exécution. `[P]` = parallélisable avec la précédente.
> **Portée M1** : les éléments `[M3]` (étapes `th signal` / `th paper` du daily, `weekly-train.yml`) seront découpés
> après complément du plan.
> Toutes les tâches tournent sous `--disable-socket`. Seules T7 (récupération des SHA d'actions, `gh api`) et T13
> (runs réels sur GitHub) utilisent le réseau, hors `pytest`.
> « Qualité verte » = `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/ && uv run pytest` sortent en 0.

## `git_sha` du manifest (modification de F08 R11)

- [x] **T1** `resolve_git_sha` : `TH_GIT_SHA` > `git rev-parse HEAD` > `GITHUB_SHA` > `None` — R8
  - Tests : `tests/export/test_dashboard.py::test_git_sha_th_git_sha_first` (les trois sources présentes),
    `::test_git_sha_repo_head_before_github_sha` (dépôt git temporaire + `GITHUB_SHA` différent → HEAD),
    `::test_git_sha_github_sha_fallback_outside_git` (`GIT_CEILING_DIRECTORIES`), `::test_git_sha_invalid_env_ignored`
    (adapté : `TH_GIT_SHA` et `GITHUB_SHA` invalides ignorés) ; `test_git_sha_from_env` remplacé par les précédents.
  - Fichiers : `src/tradinghelper/export/dashboard.py` (`resolve_git_sha`, docstring), `tests/export/test_dashboard.py`.
  - Fini quand : tests verts ; les autres tests `git_sha` (`test_cli_export.py`) inchangés et verts ; qualité verte.

## Message de commit (`th commit-message`)

- [x] **T2** `storage.read_run_reports` — R5
  - Tests : `tests/data/test_storage.py::test_read_run_reports_all_valid` (deux rapports, ordre des noms),
    `::test_read_run_reports_missing_dir_is_empty`, `::test_read_run_reports_invalid_raises` (JSON invalide, puis
    rapport hors contrat → `RunReportError` citant le fichier), `::test_read_run_reports_ignores_non_dated_files`
    (`notes.txt`, `.x.json.tmp`).
  - Fichiers : `src/tradinghelper/data/storage.py`, `tests/data/test_storage.py`.
  - Fini quand : tests verts ; la lecture des rapports par l'export (F08) n'a pas changé de comportement
    (`tests/export/` vert) ; qualité verte.

- [x] **T3** `build_commit_message` (pur) — R5
  - Tests : `tests/orchestration/test_commit_message.py::test_daily_without_rewrite`
    (`data: daily update 2026-11-23`), `::test_rewrite_symbols_sorted_deduplicated` (MSFT, AAPL, AAPL sur deux entrées
    → `(history rewrite: AAPL, MSFT)`), `::test_entries_before_since_ignored`, `::test_entry_at_since_included`
    (borne `>=`), `::test_backfill_and_model_prefixes`, `::test_fallback_session_without_recent_entry`,
    `::test_session_of_most_recent_entry` (deux rapports récents de séances différentes) ;
    `tests/test_repo_hygiene.py::test_commit_message_module_is_pure` (ni `os`, ni `pathlib`, ni `subprocess`,
    ni `tradinghelper.data.storage`, aucun `open`).
  - Fichiers : `src/tradinghelper/orchestration/__init__.py`, `src/tradinghelper/orchestration/commit_message.py`,
    `tests/orchestration/__init__.py` si nécessaire, `tests/orchestration/test_commit_message.py`, `tests/test_repo_hygiene.py`.
  - Fini quand : tests verts ; qualité verte.

- [x] **T4** Commande `th commit-message --kind … --since …` — R5
  - Tests : `tests/test_cli_commit_message.py::test_prints_message_from_reports` (fixtures sous `TH_DATA_DIR`, une ligne
    sur stdout), `::test_no_runs_dir_uses_current_session` (horloge injectée via `cli._now`),
    `::test_invalid_report_exits_1` (fichier cité sur stderr), `::test_invalid_since_exits_2[sans-fuseau|mal-forme]`,
    `::test_unknown_kind_exits_2`, `::test_runs_without_config` (`TH_CONFIG_DIR` invalide → code 0).
  - Fichiers : `src/tradinghelper/cli.py` (commande, `CONFIG_EXEMPT_COMMANDS`), `tests/test_cli_commit_message.py`.
  - Fini quand : tests verts ; `uv run th commit-message --help` affiche les deux options ; qualité verte.

## Script de commit et push

- [x] **T5** `commit-and-push.sh` : commit conditionnel, chemins limités, identité du bot — R3
  - Préalable : `.gitattributes` : `*.sh text eol=lf` ; test `tests/test_repo_hygiene.py::test_gitattributes_forces_lf`
    étendu à `sh`.
  - Tests (helper qui crée un dépôt distant `git init --bare` + un clone dans `tmp_path`, `skipif` sans `bash`) :
    `tests/test_commit_and_push.py::test_untracked_file_is_committed` (nouveau `data/runs/2026-11-23.json`),
    `::test_no_change_no_commit_empty_pushed_sha`, `::test_only_given_paths_are_committed` (un fichier modifié hors
    `data/` reste non commité), `::test_author_is_github_actions_bot` (nom et e-mail exacts),
    `::test_outputs_written_to_github_output` (`pushed_sha` et `head_sha` dans le fichier pointé par `GITHUB_OUTPUT`).
  - Fichiers : `scripts/ci/commit-and-push.sh`, `.gitattributes`, `tests/test_commit_and_push.py`, `tests/test_repo_hygiene.py`.
  - Fini quand : tests verts sous Git Bash en local ; `git ls-files --eol scripts/ci/commit-and-push.sh` montre `i/lf` ;
    qualité verte.

- [ ] **T6** `commit-and-push.sh` : `pull --rebase` + push, 3 tentatives — R4
  - Tests : `test_commit_and_push.py::test_rebases_over_concurrent_push` (un autre clone pousse un commit sur un autre
    fichier entre-temps → historique linéaire, les deux commits présents sur le distant),
    `::test_fails_after_three_attempts` (distant rendu inaccessible ou hook `pre-receive` qui refuse ; `TH_PUSH_SLEEP=0`
    ; code ≠ 0, 3 tentatives tracées sur stderr), `::test_rebase_conflict_is_aborted` (conflit sur le même fichier → aucun
    rebase en cours après l'échec).
  - Fichiers : `scripts/ci/commit-and-push.sh`, `tests/test_commit_and_push.py`.
  - Fini quand : tests verts ; qualité verte.

## Workflows

- [ ] **T7** `deploy-pages.yml` — R1, R2, R8, R10, R11, R12
  - Préalable : SHA des actions `actions/upload-pages-artifact` et `actions/deploy-pages` récupérés depuis leurs
    releases officielles (`gh api`), commentaire `# vX.Y.Z` ; `checkout`, `setup-uv`, `setup-node` aux mêmes SHA que `ci.yml`.
  - Tests : `tests/test_workflows.py` (helpers de lecture YAML mutualisés, clé `on` corrigée comme dans
    `test_repo_hygiene.py`) : `::test_workflow_level_permissions[deploy-pages]`, `::test_deploy_pages_uses_own_group`,
    `::test_deploy_pages_push_paths`, `::test_deploy_checks_out_ref_and_sets_th_git_sha`,
    `::test_deploy_pages_builds_with_base_and_checks_dist` (`TH_DASHBOARD_BASE` via `github.event.repository.name`,
    `npm run check:dist`, artefact `dashboard/dist`), `::test_actions_pinned_by_sha[deploy-pages]`,
    `::test_job_timeouts[deploy-pages]` (15).
  - Fichiers : `.github/workflows/deploy-pages.yml`, `tests/test_workflows.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T8** `daily.yml` : job `pipeline` — R1, R2, R4, R5, R6, R7, R11, R12
  - Tests : `test_workflows.py::test_workflow_level_permissions[daily]`, `::test_job_permissions_match_table[daily]`,
    `::test_data_writers_share_group[daily]`, `::test_daily_triggers` (cron `30 22 * * 1-5`, `workflow_dispatch`),
    `::test_pipeline_step_order[daily]` (ingest → validate → commit), `::test_ingest_exit_2_stops_and_1_continues`
    (script de l'étape : `set +e`, output `exit_code`, seul le code 1 est absorbé), `::test_validate_step_not_continue_on_error`,
    `::test_commit_step_only_on_main`, `::test_commit_uses_commit_message_and_data_path` (`--kind daily --since`, chemin
    `data/` seul, jamais `dashboard/public/data`), `::test_report_artifact_always_uploaded[daily]`,
    `::test_actions_pinned_by_sha[daily]`, `::test_job_timeouts[daily]` (pipeline 30).
  - Fichiers : `.github/workflows/daily.yml`, `tests/test_workflows.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T9** `daily.yml` : jobs `deploy` et `conclude` — R1, R7, R9
  - Tests : `test_workflows.py::test_caller_job_grants_pages_permissions[daily]`, `::test_deploy_condition[daily]`
    (`pushed_sha` non vide, ou `workflow_dispatch` sur `refs/heads/main`), `::test_deploy_ref_is_pushed_or_head_sha`,
    `::test_conclude_runs_always`, `::test_conclude_fails_on_ingest_exit_1`,
    `::test_conclude_fails_when_pipeline_or_deploy_failed`, `::test_job_timeouts[daily]` (conclude).
  - Fichiers : `.github/workflows/daily.yml`, `tests/test_workflows.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T10** `backfill.yml` — R1, R2, R5, R7, R9, R11, R12, R14
  - Tests : paramètres `backfill` ajoutés aux tests de T8 et T9 (permissions, groupe, ordre, artefact, deploy,
    conclude, timeouts, SHA) ; `::test_backfill_inputs` (`symbols` chaîne facultative, `full` booléen défaut `false`,
    `start` chaîne facultative), `::test_commit_uses_commit_message_and_data_path[backfill]` (`--kind backfill`),
    `::test_no_user_input_interpolated_in_run[daily|backfill|deploy-pages]` (aucun `${{ inputs.` ni
    `${{ github.event.inputs.` dans un `run:` ; inputs passés par `env:`).
  - Fichiers : `.github/workflows/backfill.yml`, `tests/test_workflows.py`.
  - Fini quand : tests verts ; qualité verte.

## Documentation

- [ ] **T11** README « Mise en service » et limites de GitHub Actions — R13, R15
  - Tests : `tests/test_repo_hygiene.py::test_readme_has_mise_en_service_section` (Pages « GitHub Actions »,
    « Read repository contents », protection de `main` et `github-actions[bot]`, relance manuelle des trois workflows),
    `::test_readme_documents_actions_limits` (un seul run en attente par groupe, retards du cron, déploiement en échec,
    notifications) ; `::test_readme_mentions_dashboard_url_and_github_settings` adapté (plus de « Read and write
    permissions » ni de « active après F10 »).
  - Fichiers : `README.md` (section « Réglages manuels du dépôt GitHub » remplacée par « Mise en service »),
    `tests/test_repo_hygiene.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T12** [P] Documentation des commandes et de l'arborescence — R5
  - Tests : `tests/test_repo_hygiene.py::test_readme_documents_commit_message` (commande dans le tableau des commandes
    `th`), `::test_docs_list_orchestration_modules` (`CLAUDE.md` : `orchestration/commit_message.py` parmi les modules
    purs, `uv run th commit-message` ; `02-architecture.md` : `orchestration/`, `scripts/ci/`).
  - Fichiers : `README.md`, `CLAUDE.md`, `specs/02-architecture.md`, `tests/test_repo_hygiene.py`.
  - Fini quand : tests verts ; qualité verte.

## Vérification réelle

- [ ] **T13** Runs réels sur GitHub (après fusion de la PR dans `main`, réseau) — R1, R2, R6–R9, R12, R14
  - Préalable : Pages réglé sur « GitHub Actions » ; « Workflow permissions » laissé sur « Read repository contents ».
  - Étapes et preuves (liens des runs notés dans la vérification) :
    1. `workflow_dispatch` du daily sur `main` : vert, commit `data: daily update S` ou absence de commit selon les
       données, deploy exécuté ; `manifest.json` publié avec `data_as_of = S` et `git_sha` = SHA du commit poussé (ou de
       `main` sans commit) (R1, R8, R9).
    2. Deux `workflow_dispatch` du daily lancés ensemble : exécutés l'un après l'autre, aucun conflit de push (R2).
    3. `workflow_dispatch` du daily sur une branche de test : arrêt avant le commit, pas de deploy, run vert (R4, R9).
    4. Backfill `start` sans `full` → rouge sur le code 2, aucun commit ; backfill `symbols: AAPL`, `full: true` →
       commit `data: backfill … (history rewrite: AAPL)` et deploy (R5, R7, R14).
    5. Branche de test jetable avec un fichier de prix corrompu (jamais sur `main` : `data/raw/` ne se modifie pas à la
       main), `workflow_dispatch` du daily sur cette branche : run rouge, arrêt à `th validate`, artefact `data/runs/`
       présent, aucun commit, aucun deploy ; branche supprimée ensuite (R6, R7). La spec dit « sur `main` » : l'arrêt
       a lieu avant l'étape de commit, la branche de test suffit à le prouver (à noter dans la vérification).
    6. Durées des 5 premiers daily planifiés en régime normal relevées (< 15 min) (R12).
  - Fichiers : aucun (preuves dans la vérification) ; éventuellement `specs/features/F10-orchestration/spec.md` si un
    écart oblige à proposer une modification de spec.
  - Fini quand : chaque étape a un lien de run et son résultat attendu.

- [ ] **T_final** Vérification : tous les critères d'acceptation M1 de la spec, et le critère ajouté à F08 (`git_sha`)
  (→ `/spec-verify F10`)

## Couverture des exigences

| Exigence | Tâches |
|---|---|
| R1 | T7, T8, T9, T10, T13 |
| R2 | T7, T8, T10, T13 |
| R3 | T5 |
| R4 | T6, T8, T13 |
| R5 | T2, T3, T4, T8, T10, T12, T13 |
| R6 | T8, T13 |
| R7 | T8, T9, T10, T13 |
| R8 | T1, T7, T13 |
| R9 | T9, T10, T13 |
| R10 | T7 |
| R11 | T7, T8, T10 |
| R12 | T7, T8, T10, T13 |
| R13 | T11 |
| R14 | T10, T13 |
| R15 | T11 |

Toutes les exigences `[M1]` (R1–R15) sont couvertes. Non découpé : éléments `[M3]` (étapes signal/paper du daily,
`weekly-train.yml`).
