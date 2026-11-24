# Tâches — F02 Validation & qualité des données

> Généré par `/spec-tasks`. Chaque tâche est petite (≤ ~1 h), testable, et référence ses exigences.
> Ordre = ordre d'exécution. `[P]` = parallélisable avec la précédente.
> Toutes les tâches tournent sous `--disable-socket`. Seule T15 fait un appel réseau, manuel et hors `pytest`.
> « Qualité verte » = `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/ && uv run pytest` sortent en 0.

## Contrats

- [x] **T1** Modèles de la section `validate` — R8
  - Tests : `tests/test_schemas.py::test_validate_run_accepts_valid_entry`, `::test_validate_run_rules[...]`, paramétré sur :
    - `exit_code: 1` sans violation, et `exit_code: 0` avec violation → refusés ;
    - `finished_at < started_at` → refusé ;
    - avertissement avec `start > end` → refusé ;
    - `start`/`end` à `null` pour `large_move`, et renseignés pour `stale` ou `missing_file` → refusés ;
    - règle inconnue (bloquante ou d'avertissement) → refusée ;
    - `ValidateViolation.symbol` non conforme à `Symbol` (ex. `readme`) → accepté.
  - Fichiers : `src/tradinghelper/schemas.py` (`BlockingRule`, `QualityWarningRule`, `ValidateArgs`, `ValidateViolation`, `ValidateWarning`, `ValidateRun`), `tests/test_schemas.py`.
  - Fini quand : tests verts ; qualité verte.

- [x] **T2** Section `validate` dans `RunReport` et schéma régénéré — R8, R7
  - Note : la sérialisation `by_alias=True, exclude_unset=True` d'`update_run_report` (prévue en T3) est avancée ici :
    sans elle, un `ingest` sur un rapport contenant `validate` écrirait une clé `validate_`. Tests
    `tests/data/test_storage.py::test_update_report_preserves_typed_validate_section`, `::test_update_report_does_not_add_empty_validate_section`.
  - Tests : `tests/test_schemas.py::test_run_report_validate_alias_roundtrip` (JSON `validate` → `validate_` → JSON `validate`, jamais de clé `validate_`), `::test_existing_ingest_only_report_still_valid` (exemple du contrat §6 sans `validate`), `::test_run_report_dump_exclude_unset_omits_validate`, `::test_generated_schemas_match_committed` (existant).
  - Fichiers : `src/tradinghelper/schemas.py` (`RunReport.validate_` avec `alias="validate"`, `validate_by_name=True` ; docstrings mises à jour, dont la règle `schema_version`), `schemas/run_report.schema.json` (régénéré par `uv run th schemas`).
  - Fini quand :
    - aucun `UserWarning` de pydantic sur le masquage de `validate` (`pytest -W error::UserWarning` sur `test_schemas.py`) ;
    - `schemas/run_report.schema.json` contient la propriété `validate`, non requise ;
    - qualité verte.

## Stockage

- [x] **T3** Ajout générique d'une entrée au rapport de run — R7
  - Tests : `tests/data/test_storage.py::test_append_entry_creates_report_with_validate_only`, `::test_append_validate_keeps_ingest_section`, `::test_append_ingest_keeps_validate_section`, `::test_ingest_only_report_bytes_unchanged_after_ingest_append` (pas de `"validate": []` ajouté), `::test_append_entry_refuses_other_session` et `::test_append_entry_refuses_unreadable_report` (`RunReportError`, fichier intact).
  - Fichiers : `src/tradinghelper/data/storage.py` (`ReportSection`, `append_run_report_entry` avec `by_alias=True, exclude_unset=True` ; `update_run_report` devient un appel à cette fonction).
  - Fini quand : nouveaux tests et tests existants de `update_run_report` verts ; qualité verte.

- [x] **T4** [P] Liste des fichiers de prix et lecture JSON brute — R1, R5
  - Tests : `tests/data/test_storage.py::test_price_files_lists_json_sorted`, `::test_price_files_ignores_tmp_hidden_and_non_json` (`.AAPL.json.abc.tmp`, `.hidden.json`, `notes.txt`), `::test_price_files_missing_dir_is_empty`, `::test_read_json_invalid_raises` (JSON invalide, UTF-8 invalide → `PricesFileError`), `::test_read_json_returns_value`.
  - Fichiers : `src/tradinghelper/data/storage.py` (`price_files`, `read_json`).
  - Fini quand : tests verts ; qualité verte.

## Règles pures (`data/quality.py`)

- [ ] **T5** `check_rows` : forme, fichier vide et dates — R2
  - Tests : `tests/data/test_quality.py::test_blocking_rule[...]` (première moitié), paramétré sur :
    - `empty_bars` ;
    - ligne de mauvaise forme : 6 éléments, chaîne à la place d'un prix, booléen, date illisible → `schema` (avec la date si elle est lisible) ;
    - date dupliquée et date décroissante → `dates_not_increasing` ;
    - samedi et Thanksgiving 26/11/2026 → `non_session_date` ;
    - date hors plage du calendrier (1985) → `non_session_date` ;
    - date `> S` → `after_last_session`.
  - Fichiers : `src/tradinghelper/data/quality.py` (`RowCheck`, `check_rows`, constantes), `tests/data/test_quality.py`.
  - Fini quand : tests verts ; `quality.py` n'importe ni `pathlib`, ni `os`, ni `storage` (test AST dans `tests/test_repo_hygiene.py::test_quality_module_is_pure`).

- [ ] **T6** `check_rows` : prix, volume, OHLC, toutes les violations — R2
  - Tests : `tests/data/test_quality.py::test_blocking_rule[...]` (seconde moitié), paramétré sur :
    - prix à 0, prix négatif, `NaN`, `Infinity` (dont sur `adj_close`) → `non_positive_price` ;
    - `228.12345` → `not_rounded` ;
    - volume `-1` → `negative_volume` ;
    - `high < low`, `low > open`, `high < close` → `ohlc_inconsistent`.
    Ainsi que : `::test_all_violations_reported_not_only_first` (3 lignes fautives → 3 violations), `::test_multiple_rules_on_same_row` (date dupliquée + `high < low` → 2 violations), `::test_valid_rows_return_bars`, `::test_ohlc_consistent_shared_with_bars` (même prédicat utilisé par `bars.py`).
  - Fichiers : `src/tradinghelper/data/quality.py` (`ohlc_consistent`, fin de `check_rows`), `src/tradinghelper/data/bars.py` (utilise `ohlc_consistent`).
  - Fini quand : tests verts, dont tous les tests existants de `test_bars.py` ; qualité verte.

- [ ] **T7** Avertissements `large_move` et `zero_volume` — R3
  - Tests : `tests/data/test_quality.py::test_large_move_thresholds[...]`, paramétré sur :
    - +60 % → avertissement, `value = 0.6` ;
    - −30 % → avertissement ;
    - +35 % → rien ;
    - exactement +40 % → rien (seuil strict).
    Ainsi que : `::test_large_move_only_since_window_start` (la barre `t−1` peut précéder la fenêtre), `::test_large_move_single_bar_none`, `::test_zero_volume_warns_each_bar_in_window`.
  - Fichiers : `src/tradinghelper/data/quality.py` (`large_moves`, `zero_volumes`).
  - Fini quand : tests verts ; qualité verte.

- [ ] **T8** [P] Avertissements `missing_session` et `stale` — R3
  - Tests : `tests/data/test_quality.py::test_missing_sessions_grouped_in_ranges` (2 séances consécutives manquantes → 1 plage, `value = 2` ; 2 trous séparés → 2 plages), `::test_holiday_and_half_day_not_missing` (Thanksgiving 26/11/2026 absent, demi-séance du 27/11/2026 présente → rien), `::test_exceptional_closure_not_missing` (09/01/2025), `::test_stale_boundary[...]` (`S−3` → rien, `S−4` → `stale`, `value` = séances de retard).
  - Fichiers : `src/tradinghelper/data/quality.py` (`missing_sessions`, `stale`).
  - Fini quand : tests verts ; qualité verte.

## Orchestration (`data/validate.py`)

- [ ] **T9** Validation d'un fichier — R1, R2, R3
  - Tests : `tests/data/test_validate.py::test_invalid_json_is_unreadable`, `::test_missing_key_is_schema_violation`, `::test_schema_version_2_is_schema_violation`, `::test_symbol_mismatch` (`MSFT.json` contenant `symbol: "AAPL"`), `::test_safety_net_catches_what_rows_miss` (`check_rows` monkeypatché pour ne rien signaler → violation `schema`), `::test_canonical_fixture_has_no_violation`, `::test_no_warnings_when_violations`, `::test_window_vs_all_history`.
  - Fichiers : `src/tradinghelper/data/validate.py` (`FileResult`, `validate_file`), `tests/data/test_validate.py`, `tests/fixtures/validate/invalid_json.json`, `tests/fixtures/validate/symbol_mismatch/MSFT.json`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T10** Validation d'un dossier — R3, R4, R5, R6
  - Tests : `tests/data/test_validate.py::test_missing_file_warning` (symbole de l'univers et benchmark), `::test_no_prices_dir_exit_0`, `::test_orphan_stale_not_warned`, `::test_orphan_corrupted_is_violation`, `::test_symbols_option_skips_orphans`, `::test_late_ipo_no_missing_session`, `::test_jump_outside_window_needs_all_history`, `::test_results_sorted`, `::test_exit_code_reflects_violations`, `::test_raw_files_untouched` (empreintes SHA-256 avant et après).
  - Fichiers : `src/tradinghelper/data/validate.py` (`ValidateRequest`, `ValidateOutcome`, `validate`) ; si besoin, `_targets` d'`ingest.py` déplacé dans un module commun (sans changer son comportement).
  - Fini quand : tests verts, dont les tests existants d'`ingest` ; qualité verte.

- [ ] **T11** Test croisé F01 ↔ F02 — R2
  - Tests : `tests/data/test_validate.py::test_file_written_by_ingest_has_no_violation`. `ingest` est lancé avec une `FakePriceSource` qui renvoie une réponse « sale » (NaN, week-end, doublon, `high < low`, volume nul, barre après `S`), puis `validate` sur le même dossier : 0 violation, avertissement `zero_volume` présent.
  - Fichiers : `tests/data/test_validate.py`.
  - Fini quand : test vert. S'il échoue, s'arrêter : c'est une divergence entre F01 R6 et F02 R2, à traiter par une modification de spec.

## CLI

- [ ] **T12** Commande `th validate` : arguments, sorties, codes — R5, R6
  - Tests : `tests/test_cli_validate.py::test_unknown_symbol_exits_2`, `::test_config_error_exits_2`, `::test_corrupted_fixture_exits_1_with_ticker_and_date` (fixture `duplicate_and_high_lt_low.json` : stderr contient les 2 violations `SYMBOL DATE rule`), `::test_jump_fixture_warns_exit_0` (fixture `jump_plus_60.json`), `::test_summary_on_stdout`, `::test_all_history_flag`.
  - Fichiers : `src/tradinghelper/cli.py` (commande `validate`, `_parse_symbols` extrait de `_parse_request`), `tests/test_cli_validate.py`, `tests/fixtures/validate/duplicate_and_high_lt_low.json`, `tests/fixtures/validate/jump_plus_60.json`.
  - Fini quand :
    - tests verts, dont ceux de `test_cli_ingest.py` (parsing de `--symbols` inchangé) ;
    - `uv run th validate --help` décrit les deux options ;
    - qualité verte.

- [ ] **T13** Écriture conditionnelle du rapport — R7
  - Tests : `tests/test_cli_validate.py::test_appends_to_existing_report_keeps_ingest`, `::test_no_report_written_on_holiday_without_violation` (aucun fichier créé), `::test_report_written_with_exit_code_1` (rapport absent + violation → créé, `exit_code: 1`), `::test_report_named_after_session` (run à 00:30 UTC), `::test_unreadable_report_not_overwritten` (stderr, fichier intact, code de sortie inchangé), `::test_report_matches_json_schema` (validé par `RunReport`).
  - Fichiers : `src/tradinghelper/cli.py`.
  - Fini quand : tests verts ; qualité verte.

## Documentation et preuve réelle

- [ ] **T14** Documentation — R5, R8
  - Tests : `tests/test_schemas.py` (existant) : l'exemple de section `validate` du contrat §6 est accepté par `RunReport` (à ajouter au test qui lit `03-data-contracts.md`, s'il en existe un ; sinon `::test_contract_validate_example_is_valid`).
  - Fichiers :
    - `specs/03-data-contracts.md` (§6 : exemple de section `validate`) ;
    - `specs/02-architecture.md` (arborescence : `data/quality.py`) ;
    - `CLAUDE.md` (`data/validate.py` dans les modules à effets de bord ; commande `uv run th validate`) ;
    - `README.md` (section `th validate`, codes de sortie, `--all-history` ; suppression de « arrivent avec F02 »).
  - Fini quand : test vert ; la doc décrit les options, les codes de sortie et la condition d'écriture du rapport.

- [ ] **T15** Smoke test manuel sur données réelles — R2, R3, R6
  - Tests : aucun test automatisé (réseau). Dans un dossier temporaire (`TH_DATA_DIR`) :
    - `uv run th ingest --symbols AAPL,SPY` ;
    - `uv run th validate --symbols AAPL,SPY --all-history` ;
    - `uv run th validate --symbols AAPL,SPY`.
  - Fichiers : `specs/features/F02-data-quality/tasks.md` (preuve).
  - Fini quand :
    - les deux validations sortent en 0, sans violation ;
    - les avertissements `--all-history` sont relevés et expliqués (aucun `missing_session` attendu, cf. preuve de F01 T19) ;
    - le dossier temporaire est supprimé, rien n'est ajouté à `data/` dans le dépôt.

- [ ] **T_final** Vérification : tous les critères d'acceptation de la spec (→ `/spec-verify F02`) — R1–R8
  - Tests : suite complète ; chacun des 14 critères est relié à un test nommé ou à la preuve de T15.
  - Fichiers : `specs/features/F02-data-quality/spec.md` (cases cochées avec leur preuve, statut), `specs/roadmap.md`.
  - Fini quand : 14/14 critères cochés avec preuve ; qualité verte ; CI verte sur la PR.

## Couverture exigences → tâches
| Exigence | Tâches |
|---|---|
| R1 Validation par `PricesFile`, `unreadable` / `schema` / `symbol_mismatch` | T4, T9 |
| R2 Règles bloquantes, toutes les violations | T5, T6, T9, T11, T15 |
| R3 Avertissements, fenêtre récente, `--all-history` | T7, T8, T9, T10, T15 |
| R4 Orphelins : R1 et R2 seulement | T10 |
| R5 CLI, lecture seule, stdout/stderr | T4, T10, T12, T14 |
| R6 Codes de sortie | T10, T12, T15 |
| R7 Écriture conditionnelle du rapport | T2, T3, T13 |
| R8 Contenu de l'entrée `validate`, schéma | T1, T2, T14 |

8/8 exigences couvertes.

## Couverture critères d'acceptation → tâches
| Critère (spec) | Tâches |
|---|---|
| Fichier corrompu → code 1, ticker + date | T6, T12 |
| Un cas par règle bloquante | T5, T6 |
| JSON invalide, clé manquante, `schema_version: 2`, `symbol_mismatch` | T9 |
| Seuils de saut (+60 %, −30 %, +35 %) | T7, T12 |
| Saut hors fenêtre / `--all-history` | T9, T10 |
| Séances manquantes en plage ; jour férié, demi-séance, IPO tardive | T8, T10 |
| `zero_volume` ; limite `stale` | T7, T8 |
| `missing_file`, dossier absent, orphelins | T10 |
| `.tmp` et non-JSON ignorés | T4 |
| `--symbols` inconnu, erreur de config → 2 | T12 |
| Lecture seule, aucun réseau | T10 |
| Rapport existant : `validate` ajouté, `ingest` intact, schéma | T3, T13 |
| Jour férié → aucun fichier écrit | T13 |
| Code 1 → rapport avec `exit_code: 1` | T13 |

14/14 critères couverts.
