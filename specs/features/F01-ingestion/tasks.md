# Tâches — F01 Ingestion quotidienne des cours (yFinance)

> Généré par `/spec-tasks`. Chaque tâche est petite (≤ ~1 h), testable, et référence ses exigences.
> Ordre = ordre d'exécution. `[P]` = parallélisable avec la précédente.
> Toutes les tâches tournent sous `--disable-socket`. Seule T19 fait un appel réseau, manuel et hors `pytest`.
> « Qualité verte » = `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/ && uv run pytest` sortent en 0.

## Fondations

- [x] **T1** Dépendances et confinement des imports — R16, R5
  - Tests : `tests/test_repo_hygiene.py::test_provider_imports_confined` (scan AST de `src/` : `yfinance` et `pandas` importés uniquement dans `data/source.py`, `pandas_market_calendars` uniquement dans `data/calendar.py`).
  - Fichiers : `pyproject.toml` (`yfinance>=1.8`, `pandas>=3.1`, `pandas-market-calendars>=5.6` ; dev `pandas-stubs>=3.1` ; `[[tool.mypy.overrides]] ignore_missing_imports` limité à `yfinance` et `pandas_market_calendars` si nécessaire), `uv.lock`, `src/tradinghelper/data/__init__.py`, `tests/test_repo_hygiene.py`.
  - Fini quand :
    - `uv lock --check` passe ;
    - le test passe (vacuement, aucun module encore) ;
    - qualité verte.

- [x] **T2** Modèle `PricesFile` — R17, R8
  - Tests : `tests/test_schemas.py::test_prices_model_accepts_valid_file`, `::test_prices_model_rejects_rule_violations[...]`, paramétré sur : dates non croissantes, date dupliquée, prix ≤ 0, `low > min(open, close)`, `high < max(open, close)`, volume < 0, volume non entier, `columns` différentes de `PRICE_COLUMNS`, `currency` ≠ USD, clé inconnue.
  - Fichiers : `src/tradinghelper/schemas.py` (`PRICE_COLUMNS`, `Bar`, `PricesFile` et ses validateurs), `tests/test_schemas.py`.
  - Fini quand : tests verts ; qualité verte.

- [x] **T3** Modèles du rapport de run — R15, R17
  - Tests : `tests/test_schemas.py::test_run_report_roundtrip`, `::test_run_report_preserves_unknown_sections` (une section `validate` survit à `model_validate` + `model_dump`), `::test_ingest_ticker_result_enums[...]` (valeurs invalides de `status`, `mode`, `rewrite_reason`, `rule` refusées).
  - Fichiers : `src/tradinghelper/schemas.py` (`IngestTickerResult`, `IngestWarning`, `IngestArgs`, `IngestRun`, `RunReport` en `extra="allow"`).
  - Fini quand : tests verts ; l'exemple JSON du contrat §6 est accepté tel quel par `RunReport.model_validate`.

- [x] **T4** Commande `th schemas` et schémas générés — R17
  - Tests :
    - `tests/test_schemas.py::test_write_json_schemas_creates_files` (dans `tmp_path`) ;
    - `::test_generated_schemas_match_committed` (régénère en mémoire et compare à `schemas/*.schema.json`) ;
    - `::test_schemas_command_works_without_config` (`CliRunner`, `TH_CONFIG_DIR` invalide → code 0).
  - Fichiers : `src/tradinghelper/schemas.py` (`SCHEMA_MODELS`, `write_json_schemas` : JSON indenté de 2, LF, saut de ligne final), `src/tradinghelper/cli.py` (commande `schemas`, ajoutée à `CONFIG_EXEMPT_COMMANDS`), `schemas/prices.schema.json`, `schemas/run_report.schema.json` (générés).
  - Fini quand :
    - `uv run th schemas` écrit les 2 fichiers ;
    - un 2e appel ne produit aucun diff ;
    - tests verts.

## Stockage

- [x] **T5** Écriture atomique et sérialisation canonique des prix — R8
  - Tests : `tests/data/test_storage.py::test_dumps_prices_matches_canonical_fixture` (fixture écrite à la main, format du contrat §2), `::test_dumps_float_shortest_repr` (`228.1`, `231.0`, `229.7312`), `::test_roundtrip_is_byte_identical`, `::test_atomic_write_failure_keeps_original` (`os.replace` monkeypatché pour lever ; fichier d'origine identique et pas de fichier temporaire restant), `::test_atomic_write_json_format` (indentation 2, LF, saut de ligne final, UTF-8 non échappé).
  - Fichiers : `src/tradinghelper/data/storage.py` (`atomic_write_text`, `atomic_write_json`, `dumps_prices`), `tests/fixtures/prices/canonical_AAPL.json`, `tests/data/test_storage.py`.
  - Fini quand : tests verts ; qualité verte.

- [x] **T6** Lecture validée, écriture conditionnelle, dossier de données — R8, R9, R2
  - Tests : `tests/data/test_storage.py::test_read_missing_returns_none`, `::test_read_invalid_json_raises`, `::test_read_schema_violation_raises` (`PricesFileError`), `::test_write_if_changed_skips_identical_bars` (fichier non réécrit, `last_updated` inchangé, retourne `False`), `::test_write_if_changed_creates_parent_dir`, `::test_data_dir_env_override` (`TH_DATA_DIR`) et `::test_data_dir_default_repo_root`.
  - Fichiers : `src/tradinghelper/data/storage.py` (`PricesFileError`, `read_prices`, `write_prices_if_changed`, `data_dir`).
  - Fini quand : tests verts.

- [x] **T7** Mise à jour d'une section du rapport de run — R15
  - Tests : `tests/data/test_storage.py::test_update_report_creates_file`, `::test_update_report_appends_ingest_run`, `::test_update_report_preserves_other_sections` (une section `validate` préexistante est intacte), `::test_update_report_is_atomic`.
  - Fichiers : `src/tradinghelper/data/storage.py` (`update_run_report`).
  - Fini quand : tests verts ; le fichier produit est validé par `RunReport`.

## Briques métier

- [x] **T8** [P] Calendrier NYSE — R7, R3
  - Tests :
    - `tests/data/test_calendar.py::test_sessions_exclude_weekends_and_holidays` (Thanksgiving 26/11/2026) ;
    - `::test_shift_back_5_sessions_skips_holidays` ;
    - `::test_market_close_half_day_2026_11_27` (18:00 UTC) ;
    - `::test_last_closed_session[...]`, paramétré : 15 h ET un jour de séance → séance précédente ; clôture + 29 min → précédente ; clôture + 30 min → du jour ; 27/11/2026 13 h 45 ET → 27/11 ; samedi → vendredi ; 00 h 30 UTC le lendemain → veille.
  - Fichiers : `src/tradinghelper/data/calendar.py` (`NyseCalendar`, `CLOSE_MARGIN`), `tests/data/test_calendar.py`.
  - Fini quand : tests verts sans réseau ; qualité verte (wrapper typé).

- [x] **T9** [P] `PriceSource`, `YFinanceSource` et `FakePriceSource` — R16, R5, R12
  - Tests :
    - `tests/data/test_source.py::test_dot_symbol_mapped_to_dash` ;
    - `::test_download_called_with_auto_adjust_false` (`yf.download` monkeypatché : `auto_adjust=False`, `actions=False`, `progress=False`, `end = end + 1 j`, symboles convertis) ;
    - `::test_multiindex_frame_to_raw_bars` (DataFrame reproduisant la sortie réelle multi-tickers) ;
    - `::test_tz_aware_index_to_session_date` ;
    - `::test_missing_or_all_nan_symbol_omitted` ;
    - `::test_download_exception_propagates` ;
    - `tests/test_fakes.py::test_fake_source_scripting` (barres, exceptions, symboles absents, journal des appels).
  - Fichiers : `src/tradinghelper/data/source.py` (`RawBar`, `PriceSource`, `to_provider_symbol`, `YFinanceSource`), `tests/fakes.py` (`FakePriceSource`, `FakeClock`, `RecordingSleep`, générateur de barres synthétiques sur les séances NYSE), `tests/data/test_source.py`, `tests/test_fakes.py`.
  - Fini quand : tests verts ; test de confinement de T1 vert ; qualité verte.

- [x] **T10** Nettoyage des barres — R5, R6
  - Tests : `tests/data/test_bars.py::test_prices_rounded_to_4_decimals_volume_int`, `::test_drops_invalid_bars[nan|weekend|holiday|after_S|non_positive|negative_volume|high_lt_low_after_rounding]` (chaque cas : barre écartée + `IngestWarning` avec la bonne `rule` et la bonne date), `::test_dedup_keeps_last_occurrence` (+ avertissement `duplicate_date`), `::test_zero_volume_kept`, `::test_output_sorted_by_date`.
  - Fichiers : `src/tradinghelper/data/bars.py` (`Cleaned`, `clean_bars`), `tests/data/test_bars.py`.
  - Fini quand : tests verts ; toute sortie de `clean_bars` est acceptée par `PricesFile`, vérifié dans le test.

- [x] **T11** Fusion du recouvrement et détection de révision — R3, R4
  - Tests :
    - `tests/data/test_bars.py::test_merge_appends_new_bars` ;
    - `::test_merge_replaces_revised_volume_bar` (`revised = 1`) ;
    - `::test_merge_identical_overlap_counts_nothing` ;
    - `::test_merge_keeps_stored_bar_missing_from_response` (+ avertissement `missing_overlap_bar`) ;
    - `::test_needs_rewrite_on_dividend_adj_close_change` (0,3 %) ;
    - `::test_needs_rewrite_on_split_close_change` ;
    - `::test_no_rewrite_within_tolerance` (écart ≤ 1e-4) ;
    - `::test_needs_rewrite_ignores_bars_before_since`.
  - Fichiers : `src/tradinghelper/data/bars.py` (`REVISION_TOL`, `OVERLAP_SESSIONS`, `Merge`, `merge_overlap`, `needs_rewrite`).
  - Fini quand : tests verts ; fonctions pures (aucun import d'E/S dans `bars.py`).

- [x] **T12** Relances avec backoff — R10
  - Tests : `tests/data/test_ingest.py::test_with_retry_first_try` (1 tentative, aucun `sleep`), `::test_with_retry_succeeds_after_two_failures` (attentes `[2, 4]`, 3 tentatives), `::test_with_retry_gives_up_after_four_attempts` (attentes `[2, 4, 8]`, `RetryError.attempts == 4`, cause conservée).
  - Fichiers : `src/tradinghelper/data/ingest.py` (`RETRY_DELAYS`, `RetryError`, `with_retry`), `tests/data/test_ingest.py`.
  - Fini quand : tests verts.

## Orchestration `ingest`

- [x] **T13** Planification par ticker : initial, à jour, benchmark, fichier corrompu — R1, R2, R3, R9
  - Tests (`tests/data/test_ingest.py`, avec `FakePriceSource`, le vrai `NyseCalendar` et `FakeClock`) :
    - `::test_initial_run_creates_all_files_including_benchmark` (dossier `prices/` absent au départ ; fichiers conformes à `PricesFile` et à `dumps_prices`) ;
    - `::test_benchmark_start_is_min_ticker_start` ;
    - `::test_file_outside_universe_untouched` ;
    - `::test_empty_initial_response_fails` ;
    - `::test_second_run_same_session_makes_no_call_and_no_change` (aucun appel, fichiers identiques octet pour octet, `changed=False`) ;
    - `::test_corrupted_file_not_overwritten_and_message_mentions_full`.
  - Fichiers : `src/tradinghelper/data/ingest.py` (`IngestRequest`, `IngestOutcome`, `ingest()` : calcul de `S`, cible, plan par ticker, mode initial, écriture).
  - Fini quand : tests verts ; qualité verte.

- [x] **T14** Lots et relances individuelles — R11, R10, R12
  - Tests :
    - `tests/data/test_ingest.py::test_45_tickers_same_start_make_3_batch_calls` (lots de 20/20/5) ;
    - `::test_tickers_grouped_by_start_date` ;
    - `::test_ticker_missing_from_batch_retried_alone` (`attempts` cumulés) ;
    - `::test_batch_failing_entirely_falls_back_to_individual` ;
    - `::test_one_failing_ticker_does_not_block_others` (1 sur 3 lève toujours : les 2 autres sont écrits, le 3e est `failed` avec son erreur ; `attempts` compte tous les appels, groupés et individuels, où le ticker figurait) ;
    - `::test_dot_symbol_stored_under_config_name`.
  - Fichiers : `src/tradinghelper/data/ingest.py` (groupage, `with_retry` autour de chaque `fetch`, relance individuelle).
  - Fini quand : tests verts ; `RecordingSleep` montre les attentes attendues.

- [x] **T15** Mode incrémental, rattrapage et réécriture sur révision — R3, R4, R7, R6
  - Tests :
    - `tests/data/test_ingest.py::test_one_new_session_adds_one_line` (diff = exactement 1 ligne ajoutée par fichier) ;
    - `::test_three_missed_sessions_add_three_lines` ;
    - `::test_request_starts_5_sessions_before_last_date` ;
    - `::test_overlap_volume_revision_replaced_without_rewrite` ;
    - `::test_no_new_bar_when_expected_fails` ;
    - `::test_revision_triggers_full_rewrite` (`history_rewritten`, `rewrite_reason="revision"`) ;
    - `::test_rewrite_starts_at_min_of_universe_start_and_first_stored` ;
    - `::test_failed_rewrite_keeps_old_file_bytes` ;
    - `::test_at_most_one_rewrite_per_ticker` ;
    - `::test_no_bar_for_unclosed_session` (la source renvoie une barre du jour à 15 h ET → écartée) ;
    - `::test_dirty_response_writes_only_valid_bars` (avertissements dans `run.warnings`).
  - Fichiers : `src/tradinghelper/data/ingest.py` (mode incrémental : `clean_bars`, `needs_rewrite`, re-fetch complet, `merge_overlap`).
  - Fini quand : tests verts.

- [x] **T16** Backfill `full`, filtre `symbols`, code de sortie et rapport — R13, R14, R15
  - Tests :
    - `tests/data/test_ingest.py::test_full_backfill_rewrites_only_requested_symbols` (`rewrite_reason="backfill"`, 1re barre = 1re séance ≥ `start`) ;
    - `::test_full_without_start_uses_universe_start` ;
    - `::test_exit_code[all_attempted_failed→1|partial→0|none_attempted→0|corrupted_only_not_attempted→0]` ;
    - `::test_should_report[changed|failed|nothing]` ;
    - `::test_ingest_run_fields` (horodatages UTC, durée ≥ 0, `args` reflétant la requête, une entrée par ticker ciblé).
  - Fichiers : `src/tradinghelper/data/ingest.py` (mode `full`, filtre `symbols`, `exit_code`, assemblage de l'`IngestRun`).
  - Fini quand : tests verts ; qualité verte.

## CLI et documentation

- [x] **T17** Commande `th ingest` — R13, R14, R15, R16
  - Tests (`tests/test_cli_ingest.py`, `CliRunner`, `TH_CONFIG_DIR` vers `write_config`, `TH_DATA_DIR` vers `tmp_path`, `_make_source` et `_now` monkeypatchés) :
    - `::test_ingest_writes_prices_and_report_on_change` ;
    - `::test_no_report_on_holiday_or_second_run` (code 0, aucun fichier dans `runs/`, résumé sur stdout) ;
    - `::test_report_named_after_session_not_utc_date` (run à 00 h 30 UTC) ;
    - `::test_start_without_full_exits_2_no_call` ;
    - `::test_unknown_symbol_exits_2_no_call` ;
    - `::test_invalid_or_future_start_exits_2` ;
    - `::test_full_backfill_rewrites_only_target` ;
    - `::test_all_failed_exits_1` ;
    - `::test_partial_failure_exits_0` ;
    - `::test_benchmark_accepted_in_symbols`.
  - Fichiers : `src/tradinghelper/cli.py` (commande `ingest`, `_make_source`, `_now`, validation des options avant de construire la source, appel à `update_run_report` si `should_report`, résumé stdout).
  - Fini quand : tests verts ; `uv run th --help` liste `ingest` et `schemas` ; qualité verte.

- [ ] **T18** [P] Documentation — R13, R17, R16
  - Tests : `tests/test_repo_hygiene.py::test_readme_documents_ingest_and_schemas` (sections/commandes présentes).
  - Fichiers :
    - `README.md` (commandes `th ingest` avec options et codes de sortie, `th schemas`, `TH_DATA_DIR`) ;
    - `specs/02-architecture.md` (arborescence : `data/source.py`, `data/bars.py`) ;
    - `CLAUDE.md` (`data/source.py` dans la liste des modules à effets de bord ; `TH_DATA_DIR`).
  - Fini quand : test vert ; relecture des trois fichiers faite.

- [ ] **T19** Smoke test réseau manuel (non commité) — R5, R12, R11
  - Tests : aucun test automatisé (le réseau est interdit dans `pytest`). La preuve est la sortie de la commande, recopiée dans `/spec-verify`.
  - Fichiers : aucun commité. Exécution avec `TH_DATA_DIR` vers un dossier temporaire : `uv run th ingest --symbols AAPL,SPY`, puis une 2e fois.
  - Fini quand :
    - le 1er run sort en 0 et crée `AAPL.json` et `SPY.json`, conformes à `PricesFile` et qui commencent à `start` ;
    - `adj_close` ≠ `close` sur les anciennes barres (dividendes) ;
    - le 2e run ne fait aucun appel et ne modifie rien ;
    - le dossier temporaire est supprimé, rien n'est ajouté à `data/` dans le dépôt.

- [ ] **T_final** Vérification : tous les critères d'acceptation de la spec (→ `/spec-verify F01`) — R1–R17
  - Tests : suite complète ; chacun des 20 critères est relié à un test nommé ou à la preuve de T19.
  - Fichiers : `specs/features/F01-ingestion/spec.md` (cases cochées avec leur preuve, statut), `specs/roadmap.md`.
  - Fini quand : 20/20 critères cochés avec preuve ; qualité verte ; CI verte sur la PR.

## Couverture exigences → tâches
| Exigence | Tâches |
|---|---|
| R1 Périmètre (tickers + benchmark) | T13 |
| R2 Mode initial | T6, T13 |
| R3 Mode incrémental / recouvrement | T8, T11, T13, T15 |
| R4 Réécriture sur révision | T11, T15 |
| R5 `auto_adjust=False`, arrondi | T1, T9, T10, T19 |
| R6 Nettoyage des barres | T10, T15 |
| R7 Pas de séance non clôturée | T8, T15 |
| R8 Écriture atomique, canonique | T2, T5, T6 |
| R9 Fichier corrompu non écrasé | T6, T13 |
| R10 Relances | T12, T14 |
| R11 Lots de ≤ 20 | T14, T19 |
| R12 Mapping de symboles | T9, T14, T19 |
| R13 CLI `ingest` | T16, T17, T18 |
| R14 Codes de sortie | T16, T17 |
| R15 Rapport de run | T3, T7, T16, T17 |
| R16 `PriceSource`, injection | T1, T9, T17, T18 |
| R17 `schemas.py`, `th schemas` | T2, T3, T4, T18 |

17/17 exigences couvertes.
