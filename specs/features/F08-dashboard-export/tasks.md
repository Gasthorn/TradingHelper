# Tâches — F08 Export des données pour le dashboard (M1)

> Généré par `/spec-tasks`. Chaque tâche est petite (≤ ~1 h), testable, et référence ses exigences.
> Ordre = ordre d'exécution. `[P]` = parallélisable avec la précédente.
> **Portée M1** (décision 7 du plan) : R16, R17, R18 et la partie M3 de R19 seront découpées après complément du plan.
> Toutes les tâches tournent sous `--disable-socket`. Seule T24 fait un appel réseau, manuel et hors `pytest`.
> « Qualité verte » = `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/ && uv run pytest` sortent en 0.
> « Qualité dashboard verte » = `npm run lint && npm run typecheck && npm run build && npm run check:dist` sortent en 0 (dans `dashboard/`).

## Dépendances

- [x] **T1** Dépendances Python : `numpy` direct, `hypothesis` et `jsonschema` en dev — R7, R8, R1
  - Tests : `tests/test_repo_hygiene.py::test_provider_packages_importable` étendu à `numpy`, `hypothesis`, `jsonschema`
    (paramètres ajoutés, test existant).
  - Fichiers : `pyproject.toml` (`numpy>=2.5` dans `dependencies` ; `hypothesis`, `jsonschema` dans le groupe `dev`), `uv.lock`.
  - Fini quand : `uv lock --check` et `uv sync --locked` sortent en 0 ; aucun nouveau paquet de production installé
    (numpy était déjà présent via pandas) ; qualité verte.

## Indicateurs (`features/indicators.py`, pur)

- [x] **T2** `sma` et `bollinger` — R7, R8
  - Préalable : créer `tests/fixtures/export/indicators_reference.json` : une série de 30 clôtures et les valeurs attendues de
    SMA(5), SMA(20), Bollinger(20, 2) haut/bas avec écart-type de population, calculées **indépendamment** du code (tableur
    ou calcul à la main), avec la méthode notée dans le fichier.
  - Tests : `tests/features/test_indicators.py::test_sma_reference_values`, `::test_bollinger_reference_values` (1e-4),
    `::test_bollinger_population_std` (série où ddof=0 et ddof=1 diffèrent nettement), `::test_sma_warmup_is_nan` (n−1 `NaN`),
    `::test_short_series_all_nan` (longueur < n), `::test_invalid_window_raises` (n = 0, n < 0).
  - Fichiers : `src/tradinghelper/features/__init__.py`, `src/tradinghelper/features/indicators.py` (`FloatArray`, `sma`,
    `bollinger`), `tests/features/__init__.py` si nécessaire, `tests/features/test_indicators.py`.
  - Fini quand : tests verts ; `indicators.py` n'importe que `numpy` et la bibliothèque standard
    (`tests/test_repo_hygiene.py::test_indicators_module_is_pure`, ajouté : ni `pandas`, ni `os`, ni `pathlib`, ni `tradinghelper.data`) ; qualité verte.

- [x] **T3** `rsi_wilder` — R7, R8
  - Tests : `test_indicators.py::test_rsi_reference_values` (valeurs RSI(14) ajoutées à la fixture de T2, calculées au
    tableur selon Wilder), `::test_rsi_warmup_is_14_nan`, `::test_rsi_flat_series_is_50`, `::test_rsi_strictly_increasing_is_100`,
    `::test_rsi_strictly_decreasing_is_0`, `::test_rsi_bounds` (toutes les valeurs dans [0, 100]).
  - Fichiers : `src/tradinghelper/features/indicators.py` (`rsi_wilder`), `tests/features/test_indicators.py`, fixture.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T4** Propriété anti-look-ahead et warm-up des indicateurs exportés — R8
  - Tests : `test_indicators.py::test_no_lookahead` (hypothesis : série de prix positifs de longueur 1–400, `t` quelconque ;
    pour SMA20/50/200, Bollinger et RSI14, la valeur à `t` calculée sur `x[:t+1]` est égale, `NaN` compris, à celle calculée
    sur `x`), `::test_warmup_lengths[sma20=19|sma50=49|sma200=199|bb=19|rsi14=14]`.
  - Fichiers : `tests/features/test_indicators.py`.
  - Fini quand : tests verts (profil hypothesis par défaut, sans `deadline` dépassée) ; qualité verte.

## Contrats (`schemas.py`)

- [ ] **T5** [P] `Signal` et `SignalsFile` (contrat §4) — R4, R9
  - Tests : `tests/test_schemas.py::test_signals_file_contract_example_valid` (exemple du §4), `::test_signals_file_rules[...]`,
    paramétré sur : `action` hors {BUY, HOLD, SELL}, `confidence` > 1 ou < 0, `target_weight` < 0, `horizon_days` = 0,
    clé inconnue, `schema_version: 2` → refusés ; `explanation` absente → acceptée.
  - Fichiers : `src/tradinghelper/schemas.py` (`Action`, `FeatureContribution`, `Signal`, `SignalsFile`), `tests/test_schemas.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T6** Modèles `TickerFile` et `OverviewFile` — R4, R6, R10, R14
  - Tests : `test_schemas.py::test_ticker_file_contract_example_valid` (exemple du §7), `::test_ticker_series_lengths_must_match`,
    `::test_export_floats_reject_nan` (`NaN` et `Infinity` dans une colonne de prix, un indicateur, `change_1d` → refusés),
    `::test_marker_action_buy_or_sell_only` (HOLD refusé), `::test_overview_contract_example_valid`,
    `::test_overview_spark_max_60`, `::test_export_signal_extends_signal` (`model_id`, `sharpe_oos`).
  - Fichiers : `src/tradinghelper/schemas.py` (`Num`, `ExportMarker`, `TickerSeries`, `TickerFile`, `OverviewTicker`,
    `LeaderboardRow`, `ExportSignal`, `Kpis`, `OverviewFile`), `tests/test_schemas.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T7** Modèles `ManifestFile` et `HealthFile` — R4, R11, R12
  - Tests : `test_schemas.py::test_manifest_contract_example_valid`, `::test_manifest_files_sorted_and_unique`,
    `::test_manifest_sha256_16_hex`, `::test_manifest_git_sha_pattern_or_null`, `::test_health_contract_example_valid`,
    `::test_health_ticker_without_file_must_be_stale`, `::test_health_run_validate_alias_roundtrip` (clé JSON `validate`,
    jamais `validate_`, sans `UserWarning` de pydantic), `::test_health_limits` (11 runs, 101 avertissements → refusés).
  - Fichiers : `src/tradinghelper/schemas.py` (`ManifestTicker`, `ManifestStrategy`, `ManifestEntry`, `ManifestFile`,
    `HealthTicker`, `HealthIngest`, `HealthValidate`, `HealthRun`, `HealthFile`), `tests/test_schemas.py`.
  - Fini quand : tests verts ; `pytest -W error::UserWarning tests/test_schemas.py` vert ; qualité verte.

- [ ] **T8** Génération des JSON Schemas — R4
  - Tests : `test_schemas.py::test_generated_schemas_match_committed` (existant, couvre les nouveaux fichiers),
    `::test_schema_models_include_export_and_signals` (noms `signals`, `export_manifest`, `export_ticker`,
    `export_overview`, `export_health`).
  - Fichiers : `src/tradinghelper/schemas.py` (`SCHEMA_MODELS`), `schemas/*.schema.json` (régénérés par `uv run th schemas`).
  - Fini quand : `uv run th schemas` écrit 7 fichiers ; un 2e lancement ne produit aucun diff ; qualité verte.

## Construction pure (`export/build.py`)

- [ ] **T9** Rendu minifié, empreinte et arrondi — R14, R15
  - Tests : `tests/export/test_build.py::test_render_is_minified_utf8` (aucun espace hors chaînes, `é` non échappé),
    `::test_render_refuses_nan`, `::test_render_uses_json_aliases` (`validate`), `::test_digest_is_16_hex_of_sha256`,
    `::test_rounded_nan_to_none`, `::test_rounded_decimals[4|2]`, `::test_rounded_returns_python_floats`.
  - Fichiers : `src/tradinghelper/export/__init__.py`, `src/tradinghelper/export/build.py` (constantes d'arrondi, `rounded`,
    `render`, `digest`), `tests/export/test_build.py`.
  - Fini quand : tests verts ; `build.py` ne fait aucune E/S
    (`tests/test_repo_hygiene.py::test_build_module_is_pure`, ajouté : ni `os`, `pathlib`, `shutil`, `tempfile`,
    `tradinghelper.data.storage`, ni appel à `open`) ; qualité verte.

- [ ] **T10** Fiche ticker et marqueurs — R6, R8, R9, R14
  - Tests : `test_build.py::test_ticker_columns_and_lengths` (colonnes du §7, sans `adj_close` ni milieu de Bollinger),
    `::test_ticker_ohlcv_copied_from_bars`, `::test_ticker_indicators_rounded` (prix 4, RSI 2),
    `::test_short_history_sma200_all_null`, `::test_no_nan_in_output`, `::test_markers_buy_sell_only_sorted`
    (HOLD exclu ; tri date puis `strategy_id`), `::test_markers_ignore_unexported_symbols`, `::test_markers_date_from_file`.
  - Fichiers : `src/tradinghelper/export/build.py` (`build_ticker`, `collect_markers`), `tests/export/test_build.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T11** Accueil et `data_as_of` — R10, R11
  - Tests : `test_build.py::test_overview_spark_60_values`, `::test_overview_short_history_spark`, `::test_change_1d`,
    `::test_change_1d_null_single_bar`, `::test_overview_m1_sections_empty` (`leaderboard`, `latest_signals` vides,
    `kpis.best_strategy_30d` nul), `::test_data_as_of_is_min_last_date`, `::test_data_as_of_null_without_files`.
  - Fichiers : `src/tradinghelper/export/build.py` (`compute_data_as_of`, `build_overview`), `tests/export/test_build.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T12** Santé — R12
  - Tests : `test_build.py::test_health_missing_file_ticker` (`last_date` et `sessions_behind` nuls, `stale: true`),
    `::test_health_sessions_behind` (jour férié et demi-séance comptés correctement), `::test_health_stale_boundary[S-3→false|S-4→true]`,
    `::test_health_keeps_10_most_recent_runs_sorted` (12 rapports), `::test_health_summarises_last_execution_of_each_section`
    (2 exécutions `ingest` : seule la dernière compte ; section absente → `null`), `::test_health_history_rewritten_symbols`,
    `::test_health_quality_warnings_from_latest_validate` (le rapport le plus récent sans `validate` est sauté),
    `::test_health_quality_warnings_truncated_at_100` (150 → 100 et `truncated: 50`), `::test_health_last_session_is_s`.
  - Fichiers : `src/tradinghelper/export/build.py` (`build_health`, réutilise `quality.STALE_SESSIONS`), `tests/export/test_build.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T13** Manifest — R11
  - Tests : `test_build.py::test_manifest_hashes_match_files`, `::test_manifest_excludes_itself`, `::test_manifest_files_sorted`,
    `::test_manifest_tickers_order_and_dates` (ordre de `universe_targets`, première et dernière date),
    `::test_benchmark_meta_name_symbol_sector_null`, `::test_benchmark_also_in_universe_keeps_name`,
    `::test_manifest_strategies_empty_in_m1`, `::test_manifest_generated_at_and_git_sha_passthrough`.
  - Fichiers : `src/tradinghelper/export/build.py` (`SymbolMeta`, `build_manifest`), `tests/export/test_build.py`.
  - Fini quand : tests verts ; qualité verte.

## Orchestration (`export/dashboard.py`)

- [ ] **T14** [P] Générateur de données synthétiques pour les tests — R19
  - Tests : `tests/test_synthetic.py::test_generated_files_are_valid_prices` (`PricesFile.model_validate` et
    `quality.check_rows` sans violation), `::test_same_seed_same_bytes`, `::test_dates_are_nyse_sessions`.
  - Fichiers : `tests/synthetic.py` (`write_synthetic_prices(dir, symbols, sessions, rng)` : marche aléatoire géométrique
    seedée, OHLC cohérents, prix à 4 décimales, sérialisation canonique via `storage.dumps_prices`), `tests/test_synthetic.py`.
  - Fini quand : tests verts ; génération de 21 × 3 780 barres < 5 s ; qualité verte.

- [ ] **T15** Lecture des sources — R13, R3
  - Préalable : fixtures `tests/fixtures/export/signals/` (BUY le 2026-11-20, HOLD le 2026-11-21, SELL le 2026-11-23
    sur AAPL, plus `latest.json`) et `tests/fixtures/export/runs/` (rapports valides).
  - Tests : `tests/export/test_dashboard.py::test_read_sources_prices_only` (pas de `runs/` ni `signals/` → listes vides),
    `::test_orphan_price_file_not_read`, `::test_missing_universe_file_skipped`, `::test_latest_json_not_read_as_dated_signals`,
    `::test_non_matching_filenames_ignored`, `::test_only_10_most_recent_reports_read` (un 11e corrompu est ignoré),
    `::test_invalid_sources_all_listed` (prix corrompu + signal invalide + rapport récent invalide → une seule
    `ExportSourceError` avec 3 problèmes).
  - Fichiers : `src/tradinghelper/export/dashboard.py` (`SourceProblem`, `ExportSourceError`, `Sources`, `read_sources`),
    fixtures, `tests/export/test_dashboard.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T16** Garde-fou sur `--out` et remplacement du dossier — R2, R3
  - Tests : `test_dashboard.py::test_check_target_refuses[repo_root|parent_of_repo|data_root|parent_of_data_root|non_empty_without_manifest]`,
    `::test_check_target_accepts[missing_dir|empty_dir|previous_export]`, `::test_replace_dir_removes_stale_files`,
    `::test_replace_dir_creates_parent_and_subdirs` (`tickers/`), `::test_failure_during_write_keeps_previous_export`
    (écriture qui lève au 3e fichier), `::test_no_temp_dir_left_after_failure`,
    `::test_failure_after_move_restores_previous_export` (renommage final qui lève).
  - Fichiers : `src/tradinghelper/export/dashboard.py` (`ExportTargetError`, `check_target`, `replace_dir`),
    `tests/export/test_dashboard.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T17** `export()` de bout en bout et `git_sha` — R1, R9, R11, R13, R15
  - Tests : `test_dashboard.py::test_prices_only_repo_exports_m1_files` (`manifest`, `overview`, `health`, `tickers/*`
    benchmark compris ; `markers`, `leaderboard`, `latest_signals`, `strategies` vides ; pas de `portfolios/` ni `models.json`),
    `::test_signals_fixture_markers_on_aapl`, `::test_sources_untouched` (SHA-256 de tout `data/` avant/après),
    `::test_out_unchanged_when_source_invalid`, `::test_two_exports_identical_bytes` (horloge et `git_sha` figés),
    `::test_git_sha_from_env`, `::test_git_sha_from_git_repo` (dépôt git temporaire), `::test_git_sha_null_outside_git`.
  - Fichiers : `src/tradinghelper/export/dashboard.py` (`ExportOutcome`, `render_files`, `resolve_git_sha`, `export`),
    `tests/export/test_dashboard.py`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T18** [P] Validation des sorties par les JSON Schemas — R1, R4, R14
  - Tests : `tests/test_schemas.py::test_export_outputs_match_json_schemas` (`jsonschema`, Draft 2020-12, chaque fichier
    d'un export de fixtures validé par son schéma de `schemas/`), `tests/export/test_build.py::test_rounding_grid`
    (parcours de chaque fichier produit : décimales par catégorie ; une série NVDA 2010 à ~0,1 $ garde 4 décimales),
    `::test_schema_version_in_every_file`.
  - Fichiers : `tests/test_schemas.py`, `tests/export/test_build.py`.
  - Fini quand : tests verts ; qualité verte.

## CLI

- [ ] **T19** Commande `th export` — R1, R3, R11
  - Tests : `tests/test_cli_export.py::test_exports_to_default_out` (racine de dépôt temporaire),
    `::test_custom_out_and_data_dir` (`--out`, `TH_DATA_DIR`), `::test_summary_on_stdout` (fichiers, taille, plus gros
    fichier, `data_as_of`), `::test_corrupted_price_file_exits_1_and_names_file`, `::test_all_bad_sources_listed`,
    `::test_dangerous_out_exits_2`, `::test_config_error_exits_2`, `::test_generated_at_uses_injected_clock`,
    `::test_git_sha_injected`, `::test_help_lists_export`.
  - Fichiers : `src/tradinghelper/cli.py` (commande `export`, point d'injection `_git_sha`), `tests/test_cli_export.py`.
  - Fini quand : tests verts ; `uv run th export --help` documente `--out` et les codes de sortie ; qualité verte.

- [ ] **T20** Taille et durée pour 20 tickers × 15 ans — R19
  - Tests : `test_dashboard.py::test_20_tickers_15_years_sizes_and_duration` (générateur de T14, 20 tickers + SPY ×
    ≈ 3 780 séances ; `manifest` < 10 Ko, `overview` < 100 Ko, chaque `tickers/*` < 500 Ko, `health` < 20 Ko ;
    durée de `export()` < 30 s).
  - Fichiers : `tests/export/test_dashboard.py`.
  - Fini quand : test vert ; tailles mesurées notées dans le message de commit. **Si une cible est dépassée : s'arrêter et
    proposer une modification de spec** (risque identifié dans le plan).

## Dashboard

- [ ] **T21** Génération des types TypeScript — R5
  - Tests : vérification par commande (pas de test Python) : `npm run gen:types` deux fois de suite → aucun diff ;
    `npm run typecheck` vert ; un fichier temporaire `src/types/_check.ts` important `TickerFile` et accédant à
    `series.close` compile, puis est supprimé.
  - Fichiers : `dashboard/package.json` (devDependency `json-schema-to-typescript`, script `gen:types`),
    `dashboard/package-lock.json`, `dashboard/scripts/gen-types.mjs`, `dashboard/src/types/*.ts` (générés),
    `dashboard/eslint.config.js` (ignorer `src/types/`).
  - Fini quand : qualité dashboard verte ; chaque fichier généré porte l'en-tête « généré, ne pas modifier » ; un type par
    schéma de `schemas/`.

- [ ] **T22** Contrôle des types en CI — R5
  - Tests : `tests/test_repo_hygiene.py::test_ci_dashboard_job_checks_generated_types` (l'étape
    `npm run gen:types && git diff --exit-code -- src/types` est présente avant `npm run typecheck`).
  - Fichiers : `.github/workflows/ci.yml`, `tests/test_repo_hygiene.py`.
  - Fini quand : test vert ; actions toujours épinglées par SHA (`test_ci_actions_pinned_by_sha`) ; qualité verte.

## Documentation et contrôle réel

- [ ] **T23** Documentation de `th export` — R1, R3, R5
  - Tests : `tests/test_repo_hygiene.py::test_readme_documents_export` (section `th export`, `--out`, codes de sortie,
    `npm run gen:types`), `::test_docs_list_export_modules` (`CLAUDE.md` liste `export/build.py` parmi les modules purs
    et `export/dashboard.py` parmi les modules à effets de bord ; `02-architecture.md` mentionne `export/build.py`).
  - Fichiers : `README.md`, `CLAUDE.md` (modules, commande `uv run th export [--out DIR]`), `specs/02-architecture.md`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T24** Smoke test réel (manuel, réseau) — R1, R12, R19
  - Tests : aucun test automatisé (réseau interdit dans `pytest`). Procédure :
    `TH_DATA_DIR=<tmp> uv run th ingest`, `TH_DATA_DIR=<tmp> uv run th validate`, `TH_DATA_DIR=<tmp> uv run th export --out <tmp>/export`,
    puis un 2e `th export` ; `dashboard/` : `npm run dev` avec l'export copié dans `public/data/`.
  - Fichiers : aucun fichier de production ; résultat consigné dans cette tâche (tailles réelles, `data_as_of`, durée).
  - Fini quand : code 0 ; 21 fichiers `tickers/` ; tailles réelles sous les cibles ; les deux exports ne diffèrent que par
    `generated_at` ; `manifest.json` chargé sans erreur dans le navigateur.

- [ ] **T_final** Vérification : tous les critères d'acceptation M1 de la spec (→ `/spec-verify F08`)

## Couverture exigences → tâches
| Exigence | Tâches |
|---|---|
| R1 Commande, conformité aux modèles, lecture seule | T1, T17, T18, T19, T23, T24 |
| R2 Reconstruction complète du dossier | T16 |
| R3 Codes de sortie, stderr, résumé | T15, T16, T19, T23 |
| R4 Modèles dans `schemas.py`, `th schemas` | T5, T6, T7, T8, T18 |
| R5 Types TS générés, contrôle CI | T21, T22, T23 |
| R6 Fiche ticker au format colonnes | T6, T10 |
| R7 `features/indicators.py` | T1, T2, T3 |
| R8 Fenêtres passées, `null` au warm-up | T1, T2, T3, T4, T10 |
| R9 Marqueurs BUY/SELL | T5, T10, T17 |
| R10 `overview.json` (sparklines, dernier cours) | T6, T11 |
| R11 `manifest.json` | T7, T11, T13, T17, T19 |
| R12 `health.json` | T7, T12, T24 |
| R13 Source absente → vide, invalide → échec | T15, T17 |
| R14 Grille d'arrondi, JSON minifié | T6, T9, T10, T18 |
| R15 Déterminisme | T9, T17 |
| R16 `[M3]` Leaderboard, signaux enrichis, P3/P8 | — (M3, décision 7 : modèles vides typés en T6/T13) |
| R17 `[M3]` Portefeuilles | — (M3, décision 7) |
| R18 `[M3]` `models.json` | — (M3, décision 7) |
| R19 Taille et durée | T14, T20, T24 (partie M3 différée) |

16/16 exigences M1 couvertes ; R16–R18 hors de ce découpage (M3).

## Couverture critères d'acceptation M1 → tâches
| Critère (spec, M1) | Tâches |
|---|---|
| Dépôt prix seuls → code 0, fichiers M1, sections vides | T17 |
| Modèle pydantic **et** JSON Schema ; `schemas/` synchronisé | T8, T18 |
| `gen:types` sans diff, `typecheck` vert | T21, T22 |
| Fichier obsolète supprimé ; exception → `--out` intact, pas de temporaire | T16 |
| Prix corrompu → 1 ; config/argument → 2 ; `--out` et `TH_DATA_DIR` | T15, T19 |
| Indicateurs vs références ; RSI 50 / 100 | T2, T3 |
| Warm-up exact, historique court, aucun `NaN` | T2, T3, T4, T10 |
| Propriété hypothesis anti-look-ahead | T4 |
| Marqueurs BUY/SELL de la fixture signaux | T10, T17 |
| `spark` de 60 valeurs, `change_1d` | T11 |
| Hash et taille du manifest, `git_sha`, `data_as_of` | T11, T13, T17 |
| `health.json` : fichier absent, `stale`, 10 runs, 100 avertissements | T12 |
| Orphelin non exporté | T15 |
| Arrondis (NVDA 2010), JSON minifié | T9, T18 |
| Deux exports identiques | T17 |
| 20 tickers × 15 ans : tailles et durée | T14, T20 |
| Sources non modifiées, aucun réseau | T17 |

17/17 critères M1 couverts.
