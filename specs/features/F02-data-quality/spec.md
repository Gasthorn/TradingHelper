# F02 — Validation & qualité des données

- **Statut** : 🔍 Verifying
- **Milestone** : M1
- **Dépend de** : F01
- **Contrats** : `03-data-contracts.md` §2 (lecture), §6 (section `validate`)
- **Principes clés** : P1 (aucune barre après `S`), P5 (fichiers conformes au schéma), P7 (rapport même en échec)

## Objectif
Détecter les fichiers de prix corrompus ou suspects avant qu'ils n'alimentent features, modèles et portefeuilles :
bloquer le pipeline sur une corruption avérée, signaler sans bloquer une anomalie plausible.

## User stories
- En tant qu'owner, si un fichier de prix est corrompu (édition manuelle, bug), le daily échoue visiblement et rien n'est commité.
- En tant qu'owner, je vois dans le rapport de run (puis sur la page Health) les anomalies récentes : séances manquantes,
  sauts de cours, volumes nuls, données périmées.
- En tant qu'owner, j'audite tout l'historique d'un ticker à la demande.

## Définitions
- **`S`** : dernière séance clôturée, définie par F01 (même fonction, `now_utc` injectable).
- **Fichier de prix** : tout fichier `*.json` de `data/raw/prices/` (sous `TH_DATA_DIR`). Les autres fichiers
  (dont les temporaires `*.tmp` d'écriture atomique) sont ignorés.
- **Fenêtre récente** : les séances NYSE de `S − 9 séances` à `S` incluses (10 séances, couvre le recouvrement F01 R3).
- **Séance manquante** : séance NYSE comprise entre la première et la dernière date d'un fichier, absente du fichier.
- **Saut de cours** : barre dont `|ln(close_t / close_{t−1})| > ln(1,4)` (`close` ajusté des splits ; `t−1` = barre
  précédente du fichier). Constante `LARGE_MOVE_LOG = ln(1.4)` dans le code.
- **Stale** : fichier dont la dernière date est `< S − 3 séances NYSE`.

## Exigences

### Périmètre et règles
- **R1** `th validate` DOIT valider chaque fichier de prix avec le modèle pydantic `PricesFile` (source de vérité du
  JSON Schema `prices`), sans dépendance `jsonschema`. Un fichier illisible (JSON invalide, encodage), non conforme au
  modèle, ou dont le champ `symbol` diffère du nom du fichier est en violation bloquante.
- **R2** Le système DOIT appliquer à **tout l'historique** de chaque fichier les règles **bloquantes** suivantes et
  rapporter **toutes** les violations (symbole, date, code de règle), sans s'arrêter à la première :
  `bars` vide (`empty_bars`) ; dates non strictement croissantes ou dupliquées (`dates_not_increasing`) ;
  date qui n'est pas une séance NYSE (`non_session_date`) ; date postérieure à `S` (`after_last_session`, P1) ;
  un des 5 prix `<= 0`, NaN ou infini (`non_positive_price`) ; volume `< 0` (`negative_volume`) ;
  `low > min(open, close)` ou `high < max(open, close)` (`ohlc_inconsistent`) ; prix non arrondi à 4 décimales (`not_rounded`).
  Les violations de R1 portent les codes `unreadable`, `schema`, `symbol_mismatch`.
- **R3** Le système DOIT appliquer les règles d'**avertissement** suivantes, sans effet sur le code de sortie :
  - `missing_session` : séances manquantes, regroupées en plages consécutives (`start`, `end`) ;
  - `large_move` : saut de cours, avec la variation mesurée ;
  - `zero_volume` : barre de volume nul ;
  - `stale` : fichier périmé (toujours évalué, quelle que soit la fenêtre) ;
  - `missing_file` : symbole de l'univers ou benchmark sans fichier de prix.
  Par défaut, `missing_session`, `large_move` et `zero_volume` ne portent que sur la **fenêtre récente** ;
  avec `--all-history`, sur tout l'historique.
- **R4** Les fichiers dont le symbole n'est plus dans l'univers (conservés par F01 R1) DOIVENT être soumis à R1 et R2
  seulement (aucun avertissement R3).

### CLI et codes de sortie
- **R5** `th validate [--symbols A,B] [--all-history]` : `--symbols` restreint la validation aux symboles listés, qui
  DOIVENT appartenir à l'univers ou être le benchmark (sinon code 2, comme F01 R13). La commande n'effectue aucun appel
  réseau et ne modifie jamais `data/raw/`. Elle affiche sur stdout un résumé (fichiers vérifiés, violations, avertissements)
  et sur stderr chaque violation sous la forme `SYMBOL DATE rule: détail`.
- **R6** Codes de sortie : **2** erreur de config (F00 R10) ou d'arguments ; **1** au moins une violation bloquante ;
  **0** sinon, y compris avec des avertissements ou sans aucun fichier de prix.

### Rapport
- **R7** Le système DOIT ajouter une entrée à la section `validate` de `data/runs/{S}.json` (liste d'exécutions, comme
  `ingest`) QUAND ce fichier existe déjà **ou** qu'au moins une violation bloquante est détectée ; SINON (ex. jour férié,
  2e run sans ingestion) aucun fichier n'est écrit. L'écriture est atomique, ne modifie aucune autre section, et a lieu
  **avant** la sortie (y compris en code 1) pour que F10 puisse téléverser le rapport.
- **R8** Une entrée `validate` DOIT contenir : `started_at`, `finished_at`, `duration_s`, `args` (`symbols`, `all_history`),
  `exit_code`, `files_checked`, `violations` (`symbol`, `date` ou `null`, `rule`, `detail`) et `warnings`
  (`symbol`, `rule`, `start`, `end` — égaux pour une barre isolée, `null` pour `stale`/`missing_file` —, `value` optionnelle).
  Le modèle est défini dans `schemas.py` (section `validate` de `RunReport`) et `schemas/run_report.schema.json` est régénéré
  par `th schemas`. La section est optionnelle : les rapports existants restent valides (pas d'incrément de `schema_version`).

## Interface avec les autres features
- **F08** lit la section `validate` pour produire `health.json` ; F02 n'écrit aucun fichier d'export.
- **F10** : quand `th validate` sort en code 1, le daily ne lance pas les étapes suivantes, ne commite pas, ne déploie pas,
  téléverse le rapport (F10 R4) et échoue visiblement.
- **CI** : la détection d'un `schemas/` désynchronisé est déjà assurée par `pytest`
  (`test_schemas.py::test_generated_schemas_match_committed`, F01 R17) ; F02 n'ajoute rien à ce sujet.

## Critères d'acceptation
- [x] Fixtures « fichier corrompu » (date dupliquée, `high < low`) → code 1, les 2 violations listées avec ticker + date + règle. (R2, R6) — Preuve : `test_cli_validate.py::test_corrupted_fixture_exits_1_with_ticker_and_date` (fixture `duplicate_and_high_lt_low.json` : stderr `AAPL 2026-11-20 dates_not_increasing` et `AAPL 2026-11-23 ohlc_inconsistent`, code 1), `test_quality.py::test_multiple_rules_on_same_row`.
- [x] Un cas par règle bloquante (`empty_bars`, `non_session_date`, `after_last_session`, prix `<= 0`, volume `< 0`, `not_rounded`) → code 1. (R2) — Preuve : `test_quality.py::test_blocking_rule[...]` (13 cas) et `::test_blocking_rule_prices[...]` (10 cas) ; code 1 : `test_validate.py::test_exit_code_reflects_violations` et invariant `exit_code == 1 ⇔ violations` (`test_schemas.py::test_validate_run_rules`).
- [x] JSON invalide, clé manquante, `schema_version: 2`, `MSFT.json` contenant `symbol: "AAPL"` → code 1 (`unreadable`, `schema`, `symbol_mismatch`). (R1) — Preuve : `test_validate.py::test_invalid_json_is_unreadable`, `::test_missing_key_is_schema_violation`, `::test_schema_version_2_is_schema_violation`, `::test_symbol_mismatch` (fixture `symbol_mismatch/MSFT.json`) ; code 1 via la CLI : `test_cli_validate.py::test_undated_violation_line`.
- [x] Saut de +60 % dans la fenêtre récente → avertissement `large_move`, code 0 ; baisse de −30 % → avertissement ; hausse de +35 % → rien. (R3, R6) — Preuve : `test_quality.py::test_large_move_thresholds[...]` (+60 %, −30 %, +35 %, +40 % strict, −28,6 %), `test_cli_validate.py::test_jump_fixture_warns_exit_0` (fixture `jump_plus_60.json`, code 0).
- [x] Saut de +60 % hors fenêtre récente → aucun avertissement par défaut, avertissement avec `--all-history`. (R3) — Preuve : `test_validate.py::test_jump_outside_window_needs_all_history`, `::test_window_vs_all_history`, `test_cli_validate.py::test_all_history_flag`.
- [x] 2 séances manquantes consécutives → un seul avertissement `missing_session` (plage) ; un jour férié NYSE, une demi-séance et une introduction en bourse postérieure à `start` ne produisent aucun avertissement. (R3) — Preuve : `test_quality.py::test_missing_sessions_grouped_in_ranges`, `::test_holiday_and_half_day_not_missing` (26 et 27/11/2026), `::test_exceptional_closure_not_missing` (09/01/2025), `test_validate.py::test_late_ipo_no_missing_session`.
- [x] Volume nul → `zero_volume` ; dernière date = `S − 3 séances` → pas de `stale`, `S − 4 séances` → `stale` (`now_utc` injecté). (R3) — Preuve : `test_quality.py::test_zero_volume_warns_each_bar_in_window`, `::test_stale_boundary[S-3→rien|S-4→stale]`, `test_validate.py::test_stale_file_warned`, `::test_zero_volume_in_window` ; `now` injecté via `validate(now=…)` et `cli._now`.
- [x] Symbole de l'univers sans fichier → `missing_file`, code 0 ; dossier de prix absent → code 0. Fichier orphelin périmé → pas de `stale` ; orphelin corrompu → code 1. (R3, R4, R6) — Preuve : `test_validate.py::test_missing_file_warning`, `::test_no_prices_dir_exit_0`, `::test_orphan_stale_not_warned`, `::test_orphan_corrupted_is_violation`.
- [x] Un fichier `X.json.tmp` et un fichier non JSON dans le dossier sont ignorés. (Définitions) — Preuve : `test_storage.py::test_price_files_ignores_tmp_hidden_and_non_json` (`.AAPL.json.abc123.tmp`, `.hidden.json`, `notes.txt`, `AAPL.json.bak`, dossier `sub.json`).
- [x] `--symbols INCONNU` et erreur de config → code 2. (R5, R6) — Preuve : `test_cli_validate.py::test_unknown_symbol_exits_2[...]`, `::test_config_error_exits_2`.
- [x] Aucun fichier de `data/raw/` n'est modifié (empreintes identiques) et aucun appel réseau (`pytest-socket`). (R5) — Preuve : `test_validate.py::test_raw_files_untouched` (SHA-256 avant/après), `::test_fixture_dir_untouched` ; `--disable-socket` dans `addopts` et `test_repo_hygiene.py::test_network_is_blocked` ; réel : T15, empreintes identiques.
- [x] Rapport existant pour `S` → entrée `validate` ajoutée, section `ingest` intacte, conforme au JSON Schema `run_report`. (R7, R8) — Preuve : `test_cli_validate.py::test_appends_to_existing_report_keeps_ingest`, `::test_report_matches_json_schema`, `test_storage.py::test_append_validate_keeps_ingest_section` ; réel : T15 (sections `ingest` puis `validate`).
- [x] Jour férié sans rapport existant et sans violation → aucun fichier écrit (`git diff` vide). (R7) — Preuve : `test_cli_validate.py::test_no_report_written_on_holiday_without_violation` (Thanksgiving, aucun dossier `runs/`).
- [x] En code 1, le rapport contient l'entrée `validate` avec `exit_code: 1`. (R7) — Preuve : `test_cli_validate.py::test_report_written_with_exit_code_1`, `::test_report_named_after_session` (run à 00:30 UTC → `2026-11-24.json`).

## Hors périmètre
- Validation des autres contrats (portefeuilles, signaux, registre) : faite par les features qui les produisent.
- Liste d'exceptions acceptées (« anomalie connue ») : inutile tant que les avertissements portent sur la fenêtre récente.
- Correction automatique des données : `th ingest --symbols X --full` (F01) reste l'outil de réparation.
- Rendu des résultats : `health.json` (F08), page Health (F09).

## Dépendances introduites
Aucune (pydantic, `pandas_market_calendars` déjà présents).

## Décisions (validées le 2026-11-24)
- **Q1** Validation par le modèle pydantic `PricesFile`, sans `jsonschema` (le JSON Schema ne peut pas exprimer les règles entre champs) (R1).
- **Q2** Une violation bloquante bloque tout le commit : F01 n'écrit jamais de barre violant R2 (F01 R6, Q5), donc une violation signale une édition manuelle ou un bug qui demande une intervention humaine (R6, F10).
- **Q3** Section `validate` = liste d'exécutions, comme `ingest` ; section optionnelle rétro-compatible, donc pas d'incrément de `schema_version` (R8).
- **Q4** Le rapport n'est écrit que s'il existe déjà ou en cas de violation, pour ne pas créer de commit un jour férié (R7).
- **Q5** Avertissements de contenu limités à la fenêtre récente de 10 séances ; tout l'historique avec `--all-history` (R3).
- **Q6** Saut de cours : log-rendement symétrique sur `close`, seuil `ln(1,4)` en constante (pas dans la config).
- **Q7** Séances manquantes : entre première et dernière date du fichier, regroupées en plages ; l'après-dernière-date relève de `stale`.
- **Q8** Symbole de l'univers sans fichier : avertissement `missing_file` (l'échec est déjà dans la section `ingest`) ; orphelins : R1 et R2 seulement (R3, R4).
- **Q9** CLI : `--symbols`, `--all-history`, `TH_DATA_DIR` respecté, config requise (R5).
- **Q10** Le contrôle de synchronisation de `schemas/` est déjà assuré par `pytest` (F01 R17) ; retiré de F02.
- **Q11** Après un échec de validate, F10 arrête le daily (pas de signal, paper, commit ni déploiement) et téléverse le rapport.

## Questions ouvertes
Aucune.
