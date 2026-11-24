# Plan — F02 Validation & qualité des données

> Généré par `/spec-plan`. À relire et valider avant `/spec-tasks`.

## Résumé de l'approche
F02 ajoute la commande `th validate`, en lecture seule sur `data/raw/prices/`. Elle n'écrit que la section `validate` du
rapport de run. Le code reprend le découpage de F01 :

1. **`schemas.py`** : contrat de la section `validate` (`ValidateRun` et ses sous-modèles), ajouté à `RunReport` comme
   champ optionnel. Le nom `validate` masque la méthode `BaseModel.validate` de pydantic (avertissement à la création de
   la classe), d'où un champ Python `validate_` avec l'alias JSON `validate`.
2. **`data/quality.py`** (nouveau, **pur**) : règles bloquantes sur les lignes brutes d'un fichier (R2) et règles
   d'avertissement sur des barres valides (R3). Ni E/S ni horloge ; le calendrier est passé sous forme de fonctions.
3. **`data/storage.py`** : liste des fichiers de prix, lecture JSON brute (erreur `unreadable` distincte), et ajout
   générique d'une entrée à une section du rapport de run (réutilisé par `ingest`).
4. **`data/validate.py`** (nouveau, orchestration) : calcule `S` et la fenêtre récente, parcourt les fichiers (univers,
   benchmark, orphelins), applique R1 à R4, assemble le `ValidateRun` et décide s'il faut écrire le rapport (R7).
5. **`cli.py`** : commande `validate` (arguments, codes de sortie, stdout/stderr, écriture du rapport avant la sortie).

**Validation en deux niveaux.** `PricesFile.model_validate` s'arrête à la première barre fautive, alors que R2 exige
toutes les violations. Le fichier est donc :
1. décodé en JSON (sinon `unreadable`) ;
2. validé pour l'en-tête par un modèle « enveloppe » dont `bars` est une liste de lignes non contrôlées (sinon une
   violation `schema` par erreur, sans date) ;
3. contrôlé ligne par ligne par `check_rows` : forme et types (sinon `schema` avec la date si elle est lisible), puis
   chaque règle de R2, en continuant après une erreur ;
4. revalidé par `PricesFile.model_validate` comme **filet de sécurité** : si `check_rows` ne trouve rien mais que le
   modèle refuse le fichier, une violation `schema` est ajoutée. Cela garantit l'équivalence avec le contrat (R1).

Les avertissements (R3) ne sont calculés que sur un fichier sans violation, donc sur des `Bar` typées.

## Vérification constitution
| Principe | Impact | Comment il est respecté |
|---|---|---|
| P1 | **Fort** | Règle bloquante `after_last_session` : une barre postérieure à `S` bloque le pipeline avant features, signaux et paper trading. `S` vient de `NyseCalendar.last_closed_session` (même définition que F01), `now` injecté. |
| P2 | Aucun | Pas de logique de décision. |
| P3 | Aucun | — |
| P4 | Faible | Aucune stochasticité. Arguments journalisés (`args`). Sorties triées (symbole, date, règle) : deux runs identiques donnent le même rapport, aux horodatages près. |
| P5 | **Fort** | Chaque fichier de prix est confronté au contrat `PricesFile` (R1, filet de sécurité). `data/raw/` en lecture seule (aucune fonction d'écriture de prix appelée ; test d'empreintes). Le rapport n'est écrit que s'il existe déjà ou en cas de violation : pas de commit un jour férié. Section `validate` dans `schemas.py`, JSON Schema régénéré. Aucune donnée dérivée produite. |
| P6 | Faible | 21 fichiers × ~4 000 barres : lecture et contrôles en < 2 s. Aucun réseau, aucun secret. |
| P7 | Moyen | Le rapport est écrit **avant** la sortie, y compris en code 1 (téléversé par F10 R4). Écriture atomique. Un rapport existant illisible ou d'une autre séance n'est jamais écrasé (`RunReportError`, comportement de F01). Un fichier de prix illisible est une violation, pas un crash. |
| P8 | Aucun | Pas d'UI (F08/F09 lisent la section). |
| P9 | Fort | `mypy --strict` ; règles pures dans `quality.py`, testées exhaustivement (paramétrées par règle). Tests sous `--disable-socket`. |

## Fichiers
| Fichier | Action | Rôle |
|---|---|---|
| `src/tradinghelper/schemas.py` | modifier | `BlockingRule`, `QualityWarningRule`, `ValidateArgs`, `ValidateViolation`, `ValidateWarning`, `ValidateRun` ; champ `RunReport.validate_` (alias `validate`) ; docstring mise à jour (règle `schema_version` assouplie). |
| `schemas/run_report.schema.json` | régénérer | Via `uv run th schemas` (section `validate` optionnelle). |
| `src/tradinghelper/data/quality.py` | créer | Fonctions pures : `check_rows`, `missing_sessions`, `large_moves`, `zero_volumes`, `stale`. Constantes `LARGE_MOVE_LOG`, `RECENT_SESSIONS`, `STALE_SESSIONS`. |
| `src/tradinghelper/data/storage.py` | modifier | `price_files`, `read_json`, `append_run_report_entry` (générique) ; `update_run_report` devient un appel à ce dernier ; sérialisation du rapport `by_alias=True, exclude_unset=True`. |
| `src/tradinghelper/data/validate.py` | créer | `ValidateRequest`, `ValidateOutcome`, `validate()`, `validate_file()`. |
| `src/tradinghelper/cli.py` | modifier | Commande `validate` ; parsing de `--symbols` mutualisé avec `ingest`. |
| `tests/fixtures/validate/` | créer | Fichiers figés pour les critères d'acceptation : `duplicate_and_high_lt_low.json`, `jump_plus_60.json`, `invalid_json.json`, `symbol_mismatch/MSFT.json`. |
| `tests/data/test_quality.py` | créer | Une famille de tests par règle (R2, R3). |
| `tests/data/test_validate.py` | créer | Scénarios par dossier temporaire (univers, orphelins, fenêtre, fichiers ignorés, lecture seule). |
| `tests/test_cli_validate.py` | créer | Codes de sortie, stdout/stderr, écriture conditionnelle du rapport. |
| `tests/data/test_storage.py` | modifier | `append_run_report_entry` ; un rapport `ingest` seul reste identique octet pour octet après relecture/réécriture. |
| `tests/test_schemas.py` | modifier | Modèles `Validate*`, alias `validate`, rapports existants toujours valides. |
| `specs/03-data-contracts.md` | modifier | §6 : exemple de section `validate`. |
| `specs/02-architecture.md` | modifier | Arborescence : `data/quality.py`. |
| `CLAUDE.md` | modifier | `data/validate.py` dans les modules à effets de bord ; commande `uv run th validate`. |
| `README.md` | modifier | Section `th validate` ; suppression de la phrase « arrivent avec F02 ». |

## Interfaces / signatures
```python
# src/tradinghelper/schemas.py
BlockingRule = Literal[
    "unreadable", "schema", "symbol_mismatch", "empty_bars", "dates_not_increasing",
    "non_session_date", "after_last_session", "non_positive_price", "negative_volume",
    "ohlc_inconsistent", "not_rounded",
]
QualityWarningRule = Literal["missing_session", "large_move", "zero_volume", "stale", "missing_file"]

class ValidateArgs(_Contract):
    symbols: list[Symbol] | None
    all_history: bool

class ValidateViolation(_Contract):
    symbol: str                 # nom du fichier sans `.json` : peut ne pas être un `Symbol` valide (orphelin)
    date: date | None           # None : erreur de fichier ou d'en-tête
    rule: BlockingRule
    detail: str

class ValidateWarning(_Contract):
    symbol: Symbol
    rule: QualityWarningRule
    start: date | None          # None si et seulement si rule ∈ {stale, missing_file}
    end: date | None            # start <= end ; égaux pour une barre isolée
    value: float | None = None  # large_move : variation simple arrondie à 4 déc. ; missing_session : nb de séances ;
                                # stale : nb de séances de retard
class ValidateRun(_Contract):
    started_at: UtcDatetime
    finished_at: UtcDatetime
    duration_s: NonNegativeFloat
    args: ValidateArgs
    exit_code: Literal[0, 1]
    files_checked: NonNegativeInt
    violations: list[ValidateViolation]
    warnings: list[ValidateWarning]
    # validateurs : finished_at >= started_at ; exit_code == 1 ⇔ violations non vide

class RunReport(BaseModel):     # extra="allow", frozen, validate_by_name=True
    schema_version: Literal[1]
    session_date: date
    ingest: list[IngestRun] = Field(default_factory=list)
    validate_: list[ValidateRun] = Field(default_factory=list, alias="validate")
```

```python
# src/tradinghelper/data/quality.py   (pur)
LARGE_MOVE_LOG: Final = math.log(1.4)
RECENT_SESSIONS: Final = 10       # fenêtre récente : S − 9 … S
STALE_SESSIONS: Final = 3

@dataclass(frozen=True)
class RowCheck:
    bars: list[Bar]                    # lignes conformes (vide si au moins une violation)
    violations: list[ValidateViolation]

def check_rows(symbol: str, rows: Sequence[JsonValue], *, last_session: date,
               is_session: Callable[[date], bool]) -> RowCheck: ...                       # R2
def missing_sessions(symbol: str, bars: Sequence[Bar], sessions: Sequence[date]) -> list[ValidateWarning]: ...
    # `sessions` = séances NYSE de la zone examinée, bornée par la 1re et la dernière date du fichier ; plages consécutives
def large_moves(symbol: str, bars: Sequence[Bar], *, since: date) -> list[ValidateWarning]: ...
def zero_volumes(symbol: str, bars: Sequence[Bar], *, since: date) -> list[ValidateWarning]: ...
def stale(symbol: str, last_date: date, *, threshold: date, sessions_late: int) -> ValidateWarning | None: ...
    # threshold = calendar.shift(S, -STALE_SESSIONS) ; stale si last_date < threshold
```

```python
# src/tradinghelper/data/storage.py
def price_files(prices_dir: Path) -> dict[str, Path]: ...
    # `*.json` non cachés, triés ; clé = nom sans `.json` ; dossier absent → {}
def read_json(path: Path) -> JsonValue: ...                     # PricesFileError si illisible / JSON invalide
type ReportSection = Literal["ingest", "validate"]
def append_run_report_entry(path: Path, session: date, section: ReportSection,
                            entry: IngestRun | ValidateRun) -> None: ...
    # crée le fichier si absent ; RunReportError si illisible/invalide/autre séance ; atomique ;
    # dump by_alias=True, exclude_unset=True : une section absente n'est pas matérialisée
def update_run_report(path: Path, session: date, run: IngestRun) -> None: ...   # inchangé (wrapper)
```

```python
# src/tradinghelper/data/validate.py
@dataclass(frozen=True)
class ValidateRequest:
    symbols: tuple[str, ...] | None = None
    all_history: bool = False

@dataclass(frozen=True)
class ValidateOutcome:
    run: ValidateRun
    session: date
    @property
    def has_violations(self) -> bool: ...

@dataclass(frozen=True)
class FileResult:
    violations: list[ValidateViolation]
    warnings: list[ValidateWarning]

def validate_file(symbol: str, path: Path, *, session: date, recent_start: date,
                  calendar: NyseCalendar, in_universe: bool, all_history: bool) -> FileResult: ...
def validate(universe: UniverseConfig, request: ValidateRequest, *, calendar: NyseCalendar,
             now: Callable[[], datetime], data_root: Path) -> ValidateOutcome: ...
```

```python
# src/tradinghelper/cli.py
@app.command()
def validate(ctx: typer.Context, symbols: str | None = None, all_history: bool = False) -> None: ...
def _parse_symbols(config: AppConfig, symbols: str | None) -> tuple[str, ...] | None: ...  # extrait de _parse_request
```

### Algorithme de `validate`
1. `S = calendar.last_closed_session(now())`, `recent_start = calendar.shift(S, -(RECENT_SESSIONS - 1))`.
2. Cible = tickers de l'univers + benchmark (réutilise `ingest._targets`, déplacé dans un module commun si besoin),
   filtrée par `--symbols`. Fichiers = `price_files(data_root/raw/prices)`.
   - Symbole cible sans fichier → avertissement `missing_file`.
   - Fichier d'un symbole cible → `validate_file(in_universe=True)`.
   - Fichier hors cible → `validate_file(in_universe=False)` (R1 et R2 seulement), **sauf** avec `--symbols`, où les
     fichiers non listés sont ignorés.
3. `validate_file` : `read_json` (→ `unreadable`) ; enveloppe (→ `schema`) ; `symbol` = nom du fichier (→ `symbol_mismatch`) ;
   `check_rows` (→ R2) ; filet `PricesFile.model_validate` (→ `schema`). Sans violation et si `in_universe` :
   `stale` (toujours), puis `missing_sessions`, `large_moves`, `zero_volumes` à partir de `recent_start`
   (ou de la 1re date avec `all_history`).
4. Tri des violations et avertissements par (symbole, date, règle) ; `exit_code = 1` si violations.
5. CLI : résumé sur stdout, une ligne `SYMBOL DATE rule: détail` par violation sur stderr (`-` si pas de date). Si le
   rapport de `S` existe **ou** s'il y a des violations : `append_run_report_entry(..., "validate", run)` ; sinon
   « Rien à signaler : aucun rapport écrit. ». Puis `Exit(run.exit_code)`.

### Règles de `check_rows` (ordre d'évaluation par ligne)
`bars` vide → `empty_bars`. Pour chaque ligne : forme `[date, 5 nombres, entier]` (sinon `schema`) → date de séance
(`is_session`, `ValueError` hors plage = `non_session_date`) → `> S` → strictement après la date précédente lisible →
prix finis et `> 0` → arrondi 4 déc. → volume `>= 0` → OHLC. **Toutes** les règles violées d'une ligne sont rapportées
(pas seulement la première), pour qu'un `high < low` sur une date dupliquée produise bien deux violations.

## Traçabilité exigences → design → tests
| Exigence | Élément de design | Test(s) prévu(s) |
|---|---|---|
| R1 | `read_json`, enveloppe, `symbol_mismatch`, filet `PricesFile.model_validate` | `tests/data/test_validate.py::test_invalid_json_is_unreadable`, `::test_missing_key_is_schema_violation`, `::test_schema_version_2_is_schema_violation`, `::test_symbol_mismatch`, `::test_safety_net_catches_what_rows_miss` (monkeypatch de `check_rows`), `::test_canonical_fixture_has_no_violation` |
| R2 | `check_rows` | `tests/data/test_quality.py::test_blocking_rule[empty_bars\|duplicate\|decreasing\|non_session\|after_S\|zero_price\|nan\|negative_volume\|high_lt_low\|low_gt_open\|not_rounded\|bad_shape]`, `::test_all_violations_reported_not_only_first`, `::test_out_of_calendar_range_is_non_session` ; `test_validate.py::test_file_written_by_ingest_has_no_violation` (F01 R6 ↔ F02 R2) |
| R3 | `missing_sessions`, `large_moves`, `zero_volumes`, `stale`, `missing_file` ; fenêtre `recent_start` | `test_quality.py::test_large_move_thresholds[+60%→warn\|-30%→warn\|+35%→none]`, `::test_missing_sessions_grouped_in_ranges`, `::test_holiday_and_half_day_not_missing`, `::test_zero_volume`, `::test_stale_boundary[S-3→none\|S-4→warn]` ; `test_validate.py::test_jump_outside_window_needs_all_history`, `::test_late_ipo_no_missing_session`, `::test_missing_file_warning`, `::test_no_warnings_when_violations` |
| R4 | `in_universe=False` | `test_validate.py::test_orphan_stale_not_warned`, `::test_orphan_corrupted_is_violation`, `::test_symbols_option_skips_orphans` |
| R5 | `_parse_symbols`, lecture seule, sorties | `tests/test_cli_validate.py::test_unknown_symbol_exits_2`, `::test_violation_lines_on_stderr`, `::test_summary_on_stdout` ; `test_validate.py::test_raw_files_untouched` (SHA-256 avant/après), `::test_tmp_and_non_json_files_ignored` ; `pytest --disable-socket` |
| R6 | `exit_code` du `ValidateRun`, `ConfigError` → 2 (F00) | `test_cli_validate.py::test_exit_codes[violation→1\|warnings_only→0\|no_prices_dir→0]`, `::test_config_error_exits_2` |
| R7 | Condition « rapport existant ou violation », écriture avant `Exit` | `test_cli_validate.py::test_appends_to_existing_report_keeps_ingest`, `::test_no_report_written_on_holiday_without_violation`, `::test_report_written_with_exit_code_1`, `::test_unreadable_report_not_overwritten` ; `test_storage.py::test_append_entry_creates_report_without_ingest_key_change` |
| R8 | Modèles `Validate*`, alias, `th schemas` | `tests/test_schemas.py::test_validate_run_rules[exit_code_vs_violations\|start_le_end\|null_dates_only_for_stale_missing_file]`, `::test_run_report_validate_alias_roundtrip`, `::test_existing_ingest_only_report_still_valid`, `::test_generated_schemas_match_committed` (existant) |

## Dépendances ajoutées
Aucune. Pydantic, `pandas_market_calendars` (via `NyseCalendar`) et typer sont déjà présents. Pas de `jsonschema`
(décision Q1 de la spec), pas de `hypothesis` (les règles sont couvertes par des cas paramétrés et par le test
« fichier écrit par `ingest` → 0 violation »).

## Risques & mitigations
- **Divergence entre `bars.clean_bars` (F01) et `quality.check_rows` (F02)** : deux implémentations des mêmes règles.
  Mitigation : test croisé `test_file_written_by_ingest_has_no_violation` sur une réponse « sale » de `FakePriceSource`,
  et filet `PricesFile.model_validate`. Factoriser un prédicat commun (`ohlc_consistent`) dans `quality.py`, importé par `bars.py`.
- **Alias `validate`** : oublier `by_alias=True` à la sérialisation écrirait une clé `validate_`. Mitigation : un seul point
  de sérialisation (`append_run_report_entry`) et un test de relecture (`test_run_report_validate_alias_roundtrip`).
- **Rapports `ingest` existants modifiés** : avec un champ par défaut, `model_dump` ajouterait `"validate": []` à chaque
  réécriture par `ingest`. Mitigation : `exclude_unset=True` et un test qui vérifie que le contenu d'un rapport `ingest`
  seul est inchangé.
- **Rapport existant illisible** : la spec ne prévoit pas de code de sortie dédié. Comportement de F01 repris : message sur
  stderr, rapport non écrasé, code de sortie inchangé (voir question 3).
- **Bruit des avertissements** : `--all-history` sur 15 ans peut produire des centaines de `zero_volume` anciens. Sans
  impact sur le daily (fenêtre récente par défaut) ; le résumé stdout compte les avertissements par règle.
- **Plage du calendrier (1990–2040)** : une date hors plage est traitée en `non_session_date`, comme dans F01.
- **Jours fériés exceptionnels** (ex. 09/01/2025) : dépendent de `pandas_market_calendars` ; un test les couvre pour éviter
  un faux `missing_session`.

## ADR
Aucun ADR requis : la structure suit `02-architecture.md` (`data/validate.py` y est déjà prévu), `quality.py` en est une
précision (comme `bars.py` pour F01). L'assouplissement de la règle `schema_version` est déjà inscrit dans les contrats.

## Décisions (validées le 2026-11-24)
1. **Découpage** : règles pures dans `data/quality.py`, orchestration dans `data/validate.py` (ajouté aux modules à effets
   de bord de `CLAUDE.md`).
2. **Alias** : champ Python `validate_`, clé JSON `validate` (typé, présent dans le JSON Schema pour F08).
3. **Rapport existant illisible** : message sur stderr, rapport non écrasé, code de sortie de la validation inchangé (comme F01).
4. **Contenu de `value`** : variation simple pour `large_move`, nombre de séances pour `missing_session` et `stale`.
5. **`--symbols`** ignore les fichiers orphelins ; sans `--symbols`, ils sont validés (R4).

## Questions pour l'humain
Aucune.
