# Plan — F01 Ingestion quotidienne des cours (yFinance)

> Généré par `/spec-plan`. À relire et valider avant `/spec-tasks`.

## Résumé de l'approche
F01 ajoute la commande `th ingest`, et `th schemas` pour générer les JSON Schemas. Le code est découpé en couches pour que la logique soit testable sans réseau ni pandas :

1. **`schemas.py`** contient les contrats `PricesFile` et `RunReport` (pydantic v2). Ce sont la source de vérité de §2 et §6.
2. **`data/calendar.py`** enveloppe `pandas_market_calendars` (calendrier NYSE avec demi-séances) derrière une petite classe `NyseCalendar`. Elle fournit les séances, la « dernière séance clôturée » `S` et le décalage de N séances. Le calendrier ne fait aucun appel réseau, donc les tests utilisent le vrai.
3. **`data/source.py`** définit le protocole `PriceSource` et l'adaptateur `YFinanceSource`. **C'est le seul module qui importe `yfinance` et `pandas`.** Il renvoie des `RawBar` (dataclass Python pure), et non des DataFrames.
4. **`data/bars.py`** regroupe des fonctions **pures** : nettoyage et arrondi (R5, R6), fusion du recouvrement (R3), détection de révision (R4).
5. **`data/storage.py`** gère les effets de bord fichiers : `atomic_write_text` / `atomic_write_json`, sérialisation canonique des prix, lecture validée, mise à jour d'une section du rapport de run.
6. **`data/ingest.py`** orchestre un run : il calcule `S`, détermine le mode de chaque ticker, groupe les lots, applique les relances, fusionne, écrit les fichiers et construit le rapport. Toutes ses dépendances sont injectées (`source`, `calendar`, `now`, `sleep`, `data_dir`).
7. **`cli.py`** valide les arguments (code 2 avant tout appel réseau), construit les dépendances réelles, appelle `ingest`, écrit le rapport et renvoie le code de sortie.

Pour l'idempotence, un ticker à jour (`last_date >= S`) ne déclenche aucun appel à la source. Un fichier n'est réécrit que si son contenu canonique change. Le rapport n'est écrit que s'il y a quelque chose à signaler.

## Vérification constitution
| Principe | Impact | Comment il est respecté |
|---|---|---|
| P1 | Moyen | Aucune barre postérieure à `S` n'est écrite (R7). `S` exige `market_close + 30 min`, demi-séances comprises. Les barres partielles du jour renvoyées par yfinance sont écartées (R6). |
| P2 | Aucun | Pas de logique de décision. |
| P3 | Aucun | — |
| P4 | Moyen | Pas de stochasticité. Nouvelles dépendances verrouillées dans `uv.lock`. Rapport horodaté en UTC ; arguments du run journalisés (`args`). |
| P5 | **Fort** | Une barre par ligne, sérialisation canonique déterministe (test octet pour octet). Append-only : seules les révisions du recouvrement (R3) et les réécritures journalisées (`history_rewritten`, F10 R2) modifient l'historique. Schémas générés par `th schemas`. Aucune donnée dérivée. |
| P6 | Moyen | Run quotidien : 21 tickers → 2 appels groupés, quelques secondes. Pire cas (source indisponible) : ~5 min de relances, sous les 15 min de F10 R6. Aucun secret. |
| P7 | **Fort** | Relances 2/4/8 s par appel (R10), relance individuelle des tickers absents d'un lot (R11), isolation des échecs par ticker, écriture atomique (R8), fichier corrompu jamais écrasé (R9), ancien fichier conservé si une réécriture échoue (R4). |
| P8 | Aucun | Pas d'UI. |
| P9 | Fort | `mypy --strict` : pandas et yfinance sont confinés à `source.py`, `pandas_market_calendars` à `calendar.py`, derrière des wrappers typés. Tests 100 % hors réseau. La logique pure de `bars.py` est testée exhaustivement. |

## Fichiers
| Fichier | Action | Rôle |
|---|---|---|
| `pyproject.toml` / `uv.lock` | modifier | Dépendances `yfinance`, `pandas`, `pandas-market-calendars` ; dev `pandas-stubs` ; overrides mypy pour les paquets non typés. |
| `src/tradinghelper/schemas.py` | créer | `PricesFile`, `Bar`, `RunReport`, `IngestRun`, `IngestTickerResult`, `IngestWarning`, `SCHEMA_MODELS`. |
| `src/tradinghelper/data/__init__.py` | créer | Package. |
| `src/tradinghelper/data/calendar.py` | créer | `NyseCalendar` : `sessions`, `is_session`, `shift`, `last_closed_session`. |
| `src/tradinghelper/data/source.py` | créer | `RawBar`, `PriceSource` (Protocol), `YFinanceSource`, `to_provider_symbol`. |
| `src/tradinghelper/data/bars.py` | créer | Fonctions pures : `clean_bars`, `merge_overlap`, `needs_rewrite`. |
| `src/tradinghelper/data/storage.py` | créer | `atomic_write_text`, `atomic_write_json`, `dumps_prices`, `read_prices`, `write_prices_if_changed`, `update_run_report`. |
| `src/tradinghelper/data/ingest.py` | créer | `IngestRequest`, `ingest()`, `with_retry()`, calcul du code de sortie. |
| `src/tradinghelper/cli.py` | modifier | Commandes `ingest` et `schemas` ; `schemas` ajouté à `CONFIG_EXEMPT_COMMANDS`. |
| `schemas/prices.schema.json`, `schemas/run_report.schema.json` | créer (générés) | Contrats pour F02 et le dashboard. |
| `tests/fakes.py` | créer | `FakePriceSource` (scriptable : barres par symbole, exceptions, absences ; journal des appels), `FakeClock`, `RecordingSleep`. |
| `tests/test_schemas.py` | créer | Validation des modèles, génération des schémas, commande `th schemas`. |
| `tests/data/test_calendar.py` | créer | Séances, jours fériés, demi-séances, `S`. |
| `tests/data/test_bars.py` | créer | Nettoyage, fusion, détection de révision. |
| `tests/data/test_storage.py` | créer | Sérialisation canonique, atomicité, lecture, rapport. |
| `tests/data/test_source.py` | créer | Conversion d'une sortie `yf.download` simulée (`monkeypatch`), mapping de symboles. |
| `tests/data/test_ingest.py` | créer | Scénarios bout en bout avec `FakePriceSource` (critères d'acceptation). |
| `tests/test_cli_ingest.py` | créer | Arguments, codes de sortie, écriture du rapport via `CliRunner`. |
| `specs/02-architecture.md` | modifier | Arborescence : ajout de `data/source.py` et `data/bars.py`. |
| `CLAUDE.md` | modifier | Liste des modules à effets de bord : ajout de `data/source.py` ; mention de `TH_DATA_DIR`. |
| `README.md` | modifier | Section « Commandes `th` » : `ingest`, `schemas`. |

## Interfaces / signatures
```python
# src/tradinghelper/schemas.py
PRICE_COLUMNS: Final = ("date", "open", "high", "low", "close", "adj_close", "volume")
Bar = tuple[date, float, float, float, float, float, int]

class PricesFile(_Strict):                      # extra="forbid", frozen
    schema_version: Literal[1] = 1
    symbol: Symbol
    currency: Literal["USD"]
    source: Literal["yfinance"]
    columns: tuple[Literal["date"], ...]          # = PRICE_COLUMNS exactement (validateur)
    last_updated: AwareDatetime                    # UTC
    bars: list[Bar]
    # validateurs : dates strictement croissantes ; prix > 0 ; low <= min(o,c) ; high >= max(o,c) ; volume >= 0

class IngestTickerResult(_Strict):
    symbol: Symbol
    status: Literal["ok", "unchanged", "failed"]
    mode: Literal["initial", "incremental", "full"] | None   # None si aucun appel (à jour, fichier corrompu)
    bars_added: NonNegativeInt
    bars_revised: NonNegativeInt
    history_rewritten: bool
    rewrite_reason: Literal["revision", "backfill"] | None
    attempts: NonNegativeInt
    error: str | None

class IngestWarning(_Strict):
    symbol: Symbol
    date: date | None
    rule: Literal["nan", "non_session_date", "after_last_session", "non_positive_price",
                  "negative_volume", "ohlc_inconsistent", "duplicate_date", "missing_overlap_bar"]

class IngestArgs(_Strict):
    symbols: list[Symbol] | None
    full: bool
    start: date | None

class IngestRun(_Strict):
    started_at: AwareDatetime
    finished_at: AwareDatetime
    duration_s: NonNegativeFloat
    args: IngestArgs
    exit_code: Literal[0, 1]
    tickers: list[IngestTickerResult]
    warnings: list[IngestWarning]

class RunReport(BaseModel):
    model_config = ConfigDict(extra="allow")      # sections des autres features (validate…) préservées
    schema_version: Literal[1] = 1
    session_date: date
    ingest: list[IngestRun] = []

SCHEMA_MODELS: Final[dict[str, type[BaseModel]]] = {"prices": PricesFile, "run_report": RunReport}
def write_json_schemas(out_dir: Path) -> list[Path]: ...
```

```python
# src/tradinghelper/data/calendar.py
CLOSE_MARGIN: Final = timedelta(minutes=30)
class NyseCalendar:
    def sessions(self, start: date, end: date) -> list[date]: ...          # bornes incluses
    def is_session(self, day: date) -> bool: ...
    def shift(self, session: date, n: int) -> date: ...                    # n < 0 : n séances avant
    def market_close(self, session: date) -> datetime: ...                 # UTC, demi-séances comprises
    def last_closed_session(self, now: datetime) -> date: ...              # S
```

```python
# src/tradinghelper/data/source.py
@dataclass(frozen=True, slots=True)
class RawBar:                                    # valeurs brutes, NaN possibles, non arrondies
    date: date
    open: float; high: float; low: float; close: float; adj_close: float; volume: float

class PriceSource(Protocol):
    def fetch(self, symbols: Sequence[str], start: date, end: date) -> Mapping[str, list[RawBar]]:
        """Symboles de config en entrée et en sortie ; `end` inclus. Un symbole absent ou vide est
        omis du résultat. Lève une exception en cas d'erreur réseau / limitation de débit.
        Si AUCUN symbole demandé n'a de donnée : `SourceError` (précisé en T9 : `yf.download`
        avale les erreurs et renvoie des colonnes vides ; sans cette règle, R10 ne relancerait
        jamais un ticker en échec)."""
class SourceError(Exception): ...

def to_provider_symbol(symbol: str) -> str: ...   # "BRK.B" -> "BRK-B" (R12)
class YFinanceSource:                             # yf.download(auto_adjust=False, actions=False,
    def fetch(...) -> Mapping[str, list[RawBar]]: ...  #   group_by="ticker", progress=False, end=end+1j)
```

```python
# src/tradinghelper/data/bars.py   (pur)
REVISION_TOL: Final = 1e-4
OVERLAP_SESSIONS: Final = 5
@dataclass(frozen=True)
class Cleaned:   bars: list[Bar]; warnings: list[IngestWarning]
@dataclass(frozen=True)
class Merge:     bars: list[Bar]; added: int; revised: int; warnings: list[IngestWarning]

def clean_bars(symbol: str, raw: Sequence[RawBar], *, last_session: date,
               is_session: Callable[[date], bool]) -> Cleaned: ...                   # R5, R6
def needs_rewrite(stored: Sequence[Bar], fresh: Sequence[Bar], *, since: date) -> bool: ...  # R4
def merge_overlap(symbol: str, stored: Sequence[Bar], fresh: Sequence[Bar], *, since: date) -> Merge: ...  # R3
```

```python
# src/tradinghelper/data/storage.py
def atomic_write_text(path: Path, text: str) -> None: ...      # tmp dans le même dossier + os.replace ; LF
def atomic_write_json(path: Path, data: JsonValue) -> None: ... # indent 2, ensure_ascii=False, \n final
def dumps_prices(prices: PricesFile) -> str: ...                # sérialisation canonique (contrat §2)
class PricesFileError(Exception): ...
def read_prices(path: Path) -> PricesFile | None: ...           # None si absent ; PricesFileError si illisible/invalide
def write_prices_if_changed(path: Path, symbol: str, bars: list[Bar], now: datetime) -> bool: ...
    # ne réécrit pas si bars inchangées ; last_updated = now seulement si réécriture
def update_run_report(path: Path, session: date, run: IngestRun) -> None: ...  # append à `ingest`, autres sections intactes
def data_dir() -> Path: ...                                     # $TH_DATA_DIR > <racine>/data
```

```python
# src/tradinghelper/data/ingest.py
RETRY_DELAYS: Final = (2.0, 4.0, 8.0)
BATCH_SIZE: Final = 20
class RetryError(Exception): attempts: int; cause: BaseException
def with_retry[T](call: Callable[[], T], sleep: Callable[[float], None]) -> tuple[T, int]: ...

@dataclass(frozen=True)
class IngestRequest:
    symbols: tuple[str, ...] | None = None
    full: bool = False
    start: date | None = None

@dataclass(frozen=True)
class IngestOutcome:
    run: IngestRun
    session: date
    changed: bool                 # ≥ 1 fichier modifié
    @property
    def should_report(self) -> bool: ...   # changed or any failed (R15)

def ingest(universe: UniverseConfig, request: IngestRequest, *, source: PriceSource,
           calendar: NyseCalendar, now: Callable[[], datetime], sleep: Callable[[float], None],
           prices_dir: Path) -> IngestOutcome: ...
def exit_code(results: Sequence[IngestTickerResult], attempted: set[str]) -> Literal[0, 1]: ...  # R14
```

```python
# src/tradinghelper/cli.py
@app.command()
def ingest(symbols: str | None = None, full: bool = False, start: str | None = None) -> None: ...
@app.command()
def schemas() -> None: ...       # exemptée de config ; écrit <racine>/schemas/*.schema.json
def _make_source() -> PriceSource: ...   # point d'injection pour les tests (monkeypatch)
def _now() -> datetime: ...              # idem
```

### Algorithme de `ingest` (résumé)
1. `S = calendar.last_closed_session(now())`. Cible = `tickers + [benchmark]` (benchmark avec `start = min(start)`), filtrée par `request.symbols`.
2. Pour chaque ticker : lire le fichier. S'il est corrompu → `failed` (R9). S'il est absent → mode `initial` depuis `start`. Si `full` → mode `full` depuis `request.start or start`. Si `last_date >= S` → `unchanged`, aucun appel. Sinon → mode `incremental` depuis `calendar.shift(last_date, -5)`.
3. Grouper les tickers à télécharger par date de début, en lots de ≤ 20, puis `with_retry(source.fetch(lot, début, S))`. Un ticker absent de la réponse, ou présent dans un lot entièrement en échec, est retenté seul (R11). `attempts` cumule les tentatives.
4. `clean_bars` → selon le mode :
   - initial / full : remplacement, avec `history_rewritten` (et `rewrite_reason="backfill"`) pour `full` ;
   - incremental : si `needs_rewrite`, `fetch` complet individuel depuis `min(start, première date stockée)`, avec `history_rewritten` et `rewrite_reason="revision"`, au plus une fois ; si ce fetch échoue → `failed`, ancien fichier conservé. Sinon `merge_overlap`. Une réponse sans barre postérieure à `last_date` → `failed`.
5. `write_prices_if_changed` (atomique, canonique), puis assemblage de l'`IngestRun` et de `exit_code`.

## Traçabilité exigences → design → tests
| Exigence | Élément de design | Test(s) prévu(s) |
|---|---|---|
| R1 | `ingest` : cible = tickers + benchmark ; fichiers hors univers ignorés | `tests/data/test_ingest.py::test_initial_run_creates_all_files_including_benchmark`, `::test_benchmark_start_is_min_ticker_start`, `::test_file_outside_universe_untouched` |
| R2 | Mode `initial`, `mkdir(parents=True)`, réponse vide → `failed` | `test_ingest.py::test_initial_run_creates_all_files_including_benchmark` (dossier absent), `::test_new_ticker_downloads_full_history_only_for_it`, `::test_empty_initial_response_fails` |
| R3 | Plan par ticker, `calendar.shift(-5)`, `merge_overlap` | `test_ingest.py::test_second_run_same_session_makes_no_call_and_no_change`, `::test_one_new_session_adds_one_line`, `::test_three_missed_sessions_add_three_lines`, `::test_no_new_bar_when_expected_fails` ; `tests/data/test_bars.py::test_merge_replaces_revised_volume_bar`, `::test_merge_keeps_stored_bar_missing_from_response` |
| R4 | `needs_rewrite`, re-fetch complet unique, ancien fichier conservé en cas d'échec | `test_bars.py::test_needs_rewrite_on_dividend_adj_close_change[0.3%]`, `::test_needs_rewrite_on_split_close_change`, `::test_no_rewrite_within_tolerance` ; `test_ingest.py::test_revision_triggers_full_rewrite`, `::test_rewrite_starts_at_min_of_universe_start_and_first_stored`, `::test_failed_rewrite_keeps_old_file_bytes`, `::test_at_most_one_rewrite_per_ticker` |
| R5 | `YFinanceSource` (`auto_adjust=False`), arrondi dans `clean_bars` | `tests/data/test_source.py::test_download_called_with_auto_adjust_false`, `::test_multiindex_frame_to_raw_bars`, `::test_tz_aware_index_to_session_date` ; `test_bars.py::test_prices_rounded_to_4_decimals_volume_int` |
| R6 | `clean_bars` (règles + warnings) | `test_bars.py::test_drops_invalid_bars[nan|weekend|after_S|non_positive|negative_volume|high_lt_low]`, `::test_dedup_keeps_last_occurrence`, `::test_zero_volume_kept` ; `test_ingest.py::test_dirty_response_writes_only_valid_bars` |
| R7 | `NyseCalendar.last_closed_session` | `tests/data/test_calendar.py::test_before_close_returns_previous_session`, `::test_half_day_close_2026_11_27`, `::test_weekend_and_holiday` ; `test_ingest.py::test_no_bar_for_unclosed_session` |
| R8 | `atomic_write_text`, `dumps_prices`, `write_prices_if_changed` | `tests/data/test_storage.py::test_dumps_prices_matches_canonical_fixture`, `::test_roundtrip_is_byte_identical`, `::test_failed_write_keeps_original` (monkeypatch `os.replace` qui lève), `::test_last_updated_unchanged_when_bars_unchanged` |
| R9 | `read_prices` → `PricesFileError` → `failed` sans écriture | `test_storage.py::test_read_invalid_json_raises`, `::test_read_schema_violation_raises` ; `test_ingest.py::test_corrupted_file_not_overwritten_and_message_mentions_full` |
| R10 | `with_retry` + `sleep` injecté | `tests/data/test_ingest.py::test_retry_succeeds_after_two_failures_sleeps_2_4`, `::test_retry_gives_up_after_four_attempts_sleeps_2_4_8`, `::test_one_failing_ticker_does_not_block_others` |
| R11 | Groupage par date de début, lots ≤ 20, relance individuelle | `test_ingest.py::test_45_tickers_same_start_make_3_batch_calls`, `::test_tickers_grouped_by_start_date`, `::test_ticker_missing_from_batch_retried_alone` |
| R12 | `to_provider_symbol` dans `YFinanceSource` | `test_source.py::test_dot_symbol_mapped_to_dash` ; `test_ingest.py::test_dot_symbol_stored_under_config_name` |
| R13 | Validation des options dans `cli.ingest` avant toute construction de source | `tests/test_cli_ingest.py::test_full_backfill_rewrites_only_target`, `::test_start_without_full_exits_2_no_call`, `::test_unknown_symbol_exits_2_no_call`, `::test_future_or_invalid_start_exits_2` |
| R14 | `exit_code()` + `ConfigError` → 2 (F00) | `tests/data/test_ingest.py::test_exit_code[all_failed→1|partial→0|none_attempted→0]` ; `test_cli_ingest.py::test_all_failed_exits_1`, `::test_partial_failure_exits_0` |
| R15 | `IngestOutcome.should_report`, `update_run_report` | `test_storage.py::test_update_report_appends_and_preserves_other_sections` ; `test_cli_ingest.py::test_report_written_on_change`, `::test_no_report_on_holiday_or_second_run`, `::test_report_named_after_session_not_utc_date` (run à 00:30 UTC) |
| R16 | `PriceSource`, injection `now` / `sleep` / `_make_source` | `tests/fakes.py` utilisé partout ; tous les tests tournent sous `--disable-socket` ; `test_source.py` monkeypatche `yf.download` |
| R17 | `schemas.py`, `write_json_schemas`, `th schemas` sans config | `tests/test_schemas.py::test_prices_model_rejects_rule_violations[...]`, `::test_generated_schemas_match_committed`, `::test_schemas_command_works_without_config` ; validation `jsonschema` non requise (la conformité est testée via `PricesFile.model_validate` sur le fichier écrit) |

## Dépendances ajoutées
Versions : contrainte minimale dans `pyproject.toml`, version exacte figée par `uv.lock`.

| Paquet | Version | Justification |
|---|---|---|
| `yfinance` | ≥ 1.8 | Source de données imposée par l'architecture (gratuite, sans clé, P6). Confinée à `data/source.py`. |
| `pandas` | ≥ 3.1 | Déjà tirée par yfinance ; déclarée explicitement car `source.py` manipule le DataFrame renvoyé (import direct). Absente de la logique métier. |
| `pandas-market-calendars` | ≥ 5.6 | Calendrier NYSE **avec horaires de clôture et demi-séances** (R7), maintenu, hors ligne. Déjà retenue par `02-architecture.md`. Alternative `exchange-calendars` équivalente mais non mentionnée par l'architecture. |
| `pandas-stubs` (dev) | ≥ 3.1 | Typage de pandas pour `mypy --strict` dans `source.py`. |

Pas de `jsonschema` : la conformité est vérifiée par pydantic, plus strict que le JSON Schema (règles inter-champs). Pas de `tenacity` : la relance tient en 15 lignes testables avec un `sleep` injecté.

## Risques & mitigations
- **Limitation de débit yfinance (HTTP 429) depuis les runners GitHub** : fréquente ces derniers temps. Les lots de 20 limitent le nombre d'appels. Les relances jusqu'à 8 s peuvent ne pas suffire → l'échec est isolé et visible dans le rapport, et F02 signalera les données « stale ». Si le problème devient récurrent, on modifiera la spec (délais plus longs) plutôt que d'improviser.
- **Comportement de `yf.download` qui varie selon les versions** (MultiIndex, `auto_adjust` par défaut, erreurs avalées et seulement affichées) : paramètres toujours explicites, conversion couverte par des tests sur un DataFrame qui reproduit la forme réelle, version figée par `uv.lock`. Un smoke test manuel réseau (`uv run th ingest --symbols AAPL`) sera fait à la vérification, hors `pytest`.
- **Cache de fuseaux de yfinance** (`~/.cache/py-yfinance`, SQLite) : sans impact en CI éphémère. En local, `yf.set_tz_cache_location` n'est pas nécessaire.
- **Typage** : `yfinance` et `pandas_market_calendars` ne sont peut-être pas typés → `[[tool.mypy.overrides]] ignore_missing_imports` limité à ces deux modules, avec des wrappers à signatures strictes.
- **pandas 3** (copy-on-write, dtype `str` par défaut) : sans impact, on convertit immédiatement en `RawBar`.
- **Dividendes et bruit d'arrondi** : `REVISION_TOL = 1e-4` sur des prix arrondis à 4 décimales. Pour un prix < 1 $, le bruit d'arrondi pourrait dépasser la tolérance ; ce n'est pas le cas de l'univers actuel (grandes capitalisations). Documenté dans le code.
- **Boucle de réécriture** : si yfinance oscille d'un jour à l'autre, on réécrit chaque jour. Le diff le rend visible ; pas de garde-fou supplémentaire en v1 (conforme à la spec).
- **Fichier corrompu non « tenté »** : un ticker corrompu est `failed` sans appel, donc il n'entre pas dans le calcul « tous les tentés ont échoué » de R14 (code 0 si les autres sont à jour). C'est voulu par la spec ; F02 bloquera de toute façon sur le fichier invalide.
- **Écriture atomique sous Windows** : `os.replace` échoue si le fichier cible est ouvert par un autre processus (éditeur). En cas d'échec, le fichier temporaire est supprimé et l'erreur remonte comme échec du ticker.

## ADR
Aucun ADR requis :
- `pandas_market_calendars` est déjà inscrit dans `02-architecture.md` ;
- l'ownership du rapport de run et la journalisation des réécritures ont été tranchés dans la spec (Q1, Q3) et les contrats ;
- l'ajout de `data/source.py` et `data/bars.py` est une précision de l'arborescence, pas un choix structurant (mise à jour de `02-architecture.md` et `CLAUDE.md`).

## Décisions (validées le 2026-11-23)
1. Adaptateur yfinance dans **`data/source.py`**, ajouté à la liste des modules à effets de bord de `CLAUDE.md`.
2. Dossier de données résolu par **`TH_DATA_DIR`** > `<racine>/data`.
3. **`RunReport` en `extra="allow"`** à la racine (sections des autres features préservées).
4. **Pas de commit de données dans F01** : smoke test manuel `--symbols AAPL` non commité ; le premier commit de `data/raw/prices/` est fait par le daily (F10).

## Questions pour l'humain
Aucune.
