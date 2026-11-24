# Plan — F08 Export des données pour le dashboard

> Généré par `/spec-plan`. À relire et valider avant `/spec-tasks`.
> **Portée** : ce plan détaille les exigences `[M1]`. Les exigences `[M3]` (R16–R18 et la partie M3 de R19) ne sont
> qu'esquissées : leur conception dépend des pré-requis de contrat listés dans la spec. Le plan sera complété avant le
> découpage des tâches M3.

## Résumé de l'approche
F08 ajoute la commande `th export`, qui lit les données du dépôt **sans les modifier** et produit les fichiers du
contrat §7 dans un dossier reconstruit à chaque run. Le code suit le découpage déjà en place (pur / effets de bord) :

1. **`features/indicators.py`** (nouveau, **pur**, `numpy` seul) : `sma`, `bollinger`, `rsi_wilder` sur des tableaux
   `float64`, `NaN` pendant le warm-up. F03 le reprendra et l'étendra.
2. **`schemas.py`** : modèles des fichiers d'export (`ManifestFile`, `TickerFile`, `OverviewFile`, `HealthFile`) et
   modèle `SignalsFile` du contrat §4 (lu pour les marqueurs, voir question 1). `th schemas` génère leurs JSON Schemas.
3. **`export/build.py`** (nouveau, **pur**) : construit chaque modèle d'export à partir de données déjà chargées
   (prix, rapports, signaux), applique la grille d'arrondi, sérialise en JSON minifié et calcule les empreintes.
4. **`export/dashboard.py`** (nouveau, effets de bord) : lit et valide les fichiers source, appelle `build`, puis écrit
   tous les fichiers dans un dossier temporaire qui remplace le dossier de sortie.
5. **`cli.py`** : commande `export` (option `--out`, codes de sortie, résumé), horloge et `git_sha` injectables.
6. **Dashboard** : `json-schema-to-typescript` génère `dashboard/src/types/*.ts` depuis `schemas/`, types commités et
   contrôlés en CI.

**Rendu en mémoire, puis écriture.** Tous les fichiers sont d'abord rendus en octets (≈ 10 Mo pour 21 tickers). Le
manifest est construit en dernier, à partir des octets des autres fichiers (empreintes et tailles exactes). Rien n'est
écrit sur disque tant qu'une source est invalide : un échec de lecture ne peut donc pas toucher le dossier de sortie.

**Chaque modèle est validé à la construction.** Les fichiers sont produits via `Model.model_validate(...)` puis
`model_dump(mode="json")` : un fichier non conforme à son contrat ne peut pas être écrit (R1). Les flottants des
modèles d'export refusent `NaN` et les infinis (`allow_inf_nan=False`), et la sérialisation utilise
`json.dumps(..., allow_nan=False)` : double barrière pour R8 et R14.

## Vérification constitution
| Principe | Impact | Comment il est respecté |
|---|---|---|
| P1 | **Fort** | Indicateurs à fenêtres **passées** uniquement : `sliding_window_view` sur `x[t-n+1..t]` pour SMA et Bollinger, récurrence avant pour le RSI. Test de propriété hypothesis : indicateur à `t` sur la série tronquée à `t` == sur la série complète (R8). Aucune barre au-delà de la dernière date stockée n'est inventée. |
| P2 | Aucun en M1 | En M3, les métriques live sont calculées par `backtest/metrics.py`, jamais réimplémentées dans `export/` (R17). |
| P3 | M3 | Baselines toujours présentes dans `leaderboard` et `models.json` (R16), test dédié. En M1 : `leaderboard` vide mais typé. |
| P4 | Moyen | Aucune stochasticité dans l'export. Sortie déterministe octet pour octet à entrées, horloge et `git_sha` égaux (R15) : listes triées explicitement, ordre des champs fixé par les modèles. Le générateur de données synthétiques des tests prend un `numpy.random.Generator` seedé. `git_sha` journalisé dans le manifest. |
| P5 | **Fort** | Chaque fichier d'export est conforme à un modèle pydantic et à un JSON Schema de `schemas/` (R1, R4). Sources validées par leur contrat (`PricesFile`, `RunReport`, `SignalsFile`) : une source invalide fait échouer l'export (R13). `dashboard/public/data/` reste ignoré par git (déjà dans `.gitignore`). Aucune écriture dans `data/`. |
| P6 | Moyen | Cible < 30 s pour 20 tickers × 15 ans (R19), estimée à quelques secondes (indicateurs numpy, ≈ 80 000 barres). Aucun réseau, aucun secret. |
| P7 | Moyen | Dossier temporaire voisin puis remplacement : en cas d'échec, l'ancien export reste en place et le temporaire est supprimé (R2). Toutes les sources invalides sont listées sur stderr en une fois. |
| P8 | M3 | `latest_signals` porte `model_id` et `sharpe_oos`, le manifest relie chaque stratégie à son modèle et à sa performance (R16). Le bandeau lui-même relève de F09. |
| P9 | Fort | `mypy --strict` (numpy est typé). Fonctions pures testées unitairement (`indicators`, `build`) ; orchestration testée sur dossiers temporaires. Types TS stricts générés (R5). Tests sous `--disable-socket`. |

## Fichiers
| Fichier | Action | Rôle |
|---|---|---|
| `src/tradinghelper/features/__init__.py` | créer | Paquet `features` (vide). |
| `src/tradinghelper/features/indicators.py` | créer | `sma`, `bollinger`, `rsi_wilder` (R7, R8). |
| `src/tradinghelper/schemas.py` | modifier | Modèles `Signal`, `SignalsFile` (§4) ; modèles d'export (§7) ; `SCHEMA_MODELS` étendu. |
| `schemas/signals.schema.json`, `schemas/export_manifest.schema.json`, `schemas/export_ticker.schema.json`, `schemas/export_overview.schema.json`, `schemas/export_health.schema.json` | générer | Via `uv run th schemas` (R4). |
| `src/tradinghelper/export/__init__.py` | créer | Paquet `export` (vide). |
| `src/tradinghelper/export/build.py` | créer | Construction pure des modèles, arrondis, rendu minifié, empreintes (R6, R9–R12, R14, R15). |
| `src/tradinghelper/export/dashboard.py` | créer | Lecture des sources, garde-fous sur `--out`, rendu de tous les fichiers, remplacement du dossier, `git_sha` (R1–R3, R13). |
| `src/tradinghelper/cli.py` | modifier | Commande `export` ; points d'injection `_now` (existant) et `_git_sha` (nouveau). |
| `pyproject.toml`, `uv.lock` | modifier | `numpy` en dépendance directe ; `hypothesis` et `jsonschema` en dépendances de dev. |
| `dashboard/package.json`, `dashboard/package-lock.json` | modifier | devDependency `json-schema-to-typescript` ; script `gen:types`. |
| `dashboard/scripts/gen-types.mjs` | créer | Génère `src/types/{nom}.ts` pour chaque `../schemas/*.schema.json` ; sortie déterministe avec en-tête « généré, ne pas modifier ». |
| `dashboard/src/types/*.ts` | générer | Types TS commités (R5). |
| `dashboard/eslint.config.js` | modifier | Ignorer `src/types/` (code généré) ; il reste couvert par `npm run typecheck`. |
| `.github/workflows/ci.yml` | modifier | Job `dashboard` : étape `npm run gen:types && git diff --exit-code -- src/types` (R5). |
| `tests/synthetic.py` | créer | Générateur seedé de fichiers de prix valides (marche aléatoire géométrique, OHLC cohérents, arrondis à 4 décimales) pour N tickers × M séances NYSE (R19). |
| `tests/fixtures/export/` | créer | Fixtures figées : `indicators_reference.json` (valeurs calculées sans numpy, en fractions exactes), `signals/2026-11-19.json`, `2026-11-20.json`, `2026-11-23.json`, `latest.json`, rapports de run. |
| `tests/features/test_indicators.py` | créer | Valeurs de référence, cas limites, warm-up, propriété anti-look-ahead (R7, R8). |
| `tests/export/test_build.py` | créer | Construction de chaque fichier, arrondis, marqueurs, santé, manifest, déterminisme (R6, R9–R12, R14, R15). |
| `tests/export/test_dashboard.py` | créer | Scénarios sur dossiers temporaires : M1 prix seuls, sources invalides, remplacement du dossier, orphelins, lecture seule, taille et durée (R1–R3, R13, R19). |
| `tests/test_cli_export.py` | créer | Codes de sortie, stdout/stderr, `--out`, `TH_DATA_DIR`, `GITHUB_SHA` (R3, R11). |
| `tests/test_schemas.py` | modifier | Modèles d'export et `SignalsFile` ; validation des sorties par `jsonschema` (R1, R4). |
| `specs/02-architecture.md` | modifier | Arborescence : `export/build.py`, `features/indicators.py` déjà prévu. |
| `CLAUDE.md` | modifier | `export/build.py` parmi les modules purs, `export/dashboard.py` parmi les modules à effets de bord ; commande `uv run th export [--out DIR]`. |
| `README.md` | modifier | Section `th export` (usage local avec `npm run dev`). |

## Interfaces / signatures
```python
# src/tradinghelper/features/indicators.py   (pur, numpy uniquement)
FloatArray = npt.NDArray[np.float64]

def sma(x: FloatArray, n: int) -> FloatArray: ...
    # moyenne de x[t-n+1..t] ; NaN pour t < n-1 ; ValueError si n < 1
def bollinger(x: FloatArray, n: int = 20, k: float = 2.0) -> tuple[FloatArray, FloatArray, FloatArray]: ...
    # (milieu, haut, bas) ; écart-type de population (ddof=0) sur la même fenêtre que sma(x, n)
def rsi_wilder(x: FloatArray, n: int = 14) -> FloatArray: ...
    # NaN pour t < n ; à t = n : moyennes simples des n premières hausses/baisses ; ensuite
    # avg = (avg_prev * (n-1) + valeur) / n ; perte moyenne nulle → 100 ; gain et perte nuls → 50
```

```python
# src/tradinghelper/schemas.py   (extraits)
Num = Annotated[float, Field(allow_inf_nan=False)]           # flottant d'export, jamais NaN/inf
Action = Literal["BUY", "HOLD", "SELL"]

class Signal(_Contract):                                      # contrat §4
    strategy_id: str
    symbol: Symbol
    action: Action
    confidence: Annotated[float, Field(ge=0, le=1)]
    target_weight: Annotated[float, Field(ge=0, le=1)]
    horizon_days: PositiveInt
    explanation: list[FeatureContribution] | None = None

class SignalsFile(_Contract):
    schema_version: Literal[1]
    date: date
    generated_at: UtcDatetime
    signals: list[Signal]

class ExportMarker(_Contract):
    date: date
    strategy_id: str
    action: Literal["BUY", "SELL"]
    confidence: Num

class TickerSeries(_Contract):
    date: list[date]
    open: list[Num]; high: list[Num]; low: list[Num]; close: list[Num]
    volume: list[NonNegativeInt]
    sma20: list[Num | None]; sma50: list[Num | None]; sma200: list[Num | None]
    bb_upper: list[Num | None]; bb_lower: list[Num | None]; rsi14: list[Num | None]
    # validateur : toutes les colonnes ont la longueur de `date`

class TickerFile(_Contract):
    schema_version: Literal[1]
    symbol: Symbol
    series: TickerSeries
    markers: list[ExportMarker]

class OverviewTicker(_Contract):
    symbol: Symbol
    last_close: Num
    change_1d: Num | None
    spark: Annotated[list[Num], Field(max_length=60)]

class LeaderboardRow(_Contract):                              # rempli en M3
    strategy_id: str
    kind: Literal["baseline", "model"]
    equity: Num
    return_30d: Num | None
    sharpe_oos: Num | None
    random_percentile: Num | None

class ExportSignal(Signal):                                   # rempli en M3 (P8)
    model_id: str | None
    sharpe_oos: Num | None

class Kpis(_Contract):
    best_strategy_30d: str | None

class OverviewFile(_Contract):
    schema_version: Literal[1]
    data_as_of: date | None
    tickers: list[OverviewTicker]
    leaderboard: list[LeaderboardRow]
    latest_signals: list[ExportSignal]
    kpis: Kpis

class ManifestTicker(_Contract):
    symbol: Symbol
    name: str
    sector: str | None
    benchmark: bool
    first_date: date
    last_date: date

class ManifestStrategy(_Contract):                            # rempli en M3
    id: str
    kind: Literal["baseline", "model"]
    model_id: str | None
    sharpe_oos: Num | None

class ManifestEntry(_Contract):
    path: str                                                 # relatif, séparateur "/"
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
    bytes: NonNegativeInt

class ManifestFile(_Contract):
    schema_version: Literal[1]
    generated_at: UtcDatetime
    data_as_of: date | None
    git_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{7,40}$")] | None
    currency: Literal["USD"]
    benchmark: Symbol
    tickers: list[ManifestTicker]
    strategies: list[ManifestStrategy]
    files: list[ManifestEntry]                                # validateur : triés par path, uniques

class HealthTicker(_Contract):
    symbol: Symbol
    last_date: date | None
    sessions_behind: NonNegativeInt | None
    stale: bool                                               # validateur : last_date None ⇒ stale

class HealthIngest(_Contract):
    exit_code: Literal[0, 1]
    ok: NonNegativeInt
    unchanged: NonNegativeInt
    failed: NonNegativeInt
    history_rewritten: list[Symbol]

class HealthValidate(_Contract):
    exit_code: Literal[0, 1]
    violations: NonNegativeInt
    warnings: NonNegativeInt

class HealthRun(_Contract):                                   # validate_by_name, comme RunReport
    session_date: date
    ingest: HealthIngest | None
    validate_: HealthValidate | None = Field(alias="validate")

class HealthFile(_Contract):
    schema_version: Literal[1]
    last_session: date
    tickers: list[HealthTicker]
    runs: Annotated[list[HealthRun], Field(max_length=10)]
    quality_warnings: Annotated[list[ValidateWarning], Field(max_length=100)]
    quality_warnings_truncated: NonNegativeInt

SCHEMA_MODELS = {"prices": ..., "run_report": ..., "signals": SignalsFile,
                 "export_manifest": ManifestFile, "export_ticker": TickerFile,
                 "export_overview": OverviewFile, "export_health": HealthFile}
```

```python
# src/tradinghelper/export/build.py   (pur)
PRICE_DECIMALS: Final = 4      # prix et indicateurs de prix
RSI_DECIMALS: Final = 2
RATIO_DECIMALS: Final = 4      # ratios, rendements, poids, confiances, métriques
MONEY_DECIMALS: Final = 2      # equity, cash (M3)
SPARK_LENGTH: Final = 60
HEALTH_RUNS: Final = 10
MAX_QUALITY_WARNINGS: Final = 100

@dataclass(frozen=True)
class SymbolMeta:
    symbol: str
    name: str
    sector: str | None
    benchmark: bool

def rounded(values: FloatArray, decimals: int) -> list[float | None]: ...    # NaN → None
def build_ticker(prices: PricesFile, markers: Sequence[ExportMarker]) -> TickerFile: ...
def collect_markers(signals: Sequence[SignalsFile], symbols: Set[str]) -> dict[str, list[ExportMarker]]: ...
    # BUY/SELL seulement, symboles exportés seulement, triés (date, strategy_id)
def compute_data_as_of(last_dates: Mapping[str, date]) -> date | None: ...
def build_overview(prices: Mapping[str, PricesFile], data_as_of: date | None) -> OverviewFile: ...
def build_health(targets: Sequence[str], last_dates: Mapping[str, date], reports: Sequence[RunReport],
                 *, session: date, calendar: NyseCalendar) -> HealthFile: ...
def build_manifest(universe: UniverseConfig, metas: Sequence[SymbolMeta], prices: Mapping[str, PricesFile],
                   files: Mapping[str, bytes], *, generated_at: datetime, git_sha: str | None,
                   data_as_of: date | None) -> ManifestFile: ...
def render(model: BaseModel) -> bytes: ...
    # json.dumps(model.model_dump(mode="json", by_alias=True), separators=(",", ":"),
    #            ensure_ascii=False, allow_nan=False).encode("utf-8")
def digest(content: bytes) -> str: ...                                      # sha256 hex[:16]
```

```python
# src/tradinghelper/export/dashboard.py
MANIFEST: Final = "manifest.json"

@dataclass(frozen=True)
class SourceProblem:
    path: Path
    reason: str

class ExportSourceError(Exception):          # → code 1 ; liste de tous les fichiers fautifs
    problems: list[SourceProblem]

class ExportTargetError(Exception): ...      # --out dangereux → code 2

@dataclass(frozen=True)
class Sources:
    prices: dict[str, PricesFile]            # symboles exportés seulement, ordre de universe_targets
    reports: list[RunReport]                 # 10 plus récents, session_date décroissante
    signals: list[SignalsFile]               # data/signals/YYYY-MM-DD.json, triés par date

@dataclass(frozen=True)
class ExportOutcome:
    out: Path
    sizes: dict[str, int]                    # path -> octets, manifest compris
    data_as_of: date | None

def read_sources(universe: UniverseConfig, data_root: Path) -> Sources: ...  # ExportSourceError
def render_files(universe: UniverseConfig, sources: Sources, *, calendar: NyseCalendar,
                 now: datetime, git_sha: str | None) -> dict[str, bytes]: ...
def check_target(out: Path, *, data_root: Path, repo_root: Path) -> None: ...  # ExportTargetError
def replace_dir(out: Path, files: Mapping[str, bytes]) -> None: ...
def resolve_git_sha(environ: Mapping[str, str], repo_root: Path) -> str | None: ...
def export(universe: UniverseConfig, *, data_root: Path, out: Path, repo_root: Path,
           calendar: NyseCalendar, now: Callable[[], datetime], git_sha: str | None) -> ExportOutcome: ...
```

```python
# src/tradinghelper/cli.py
def _git_sha() -> str | None: ...            # point d'injection : resolve_git_sha(os.environ, find_repo_root())

@app.command()
def export(ctx: typer.Context, out: Path | None = None) -> None: ...
    # défaut : find_repo_root() / "dashboard" / "public" / "data"
```

### Algorithme de `export`
1. `check_target(out)` : refus (code 2) si `out` est la racine du dépôt, un de ses parents, ou s'il est égal à
   `data_root` ou le contient ; refus aussi si `out` existe, n'est pas vide et ne contient pas `manifest.json`
   (ce n'est pas un export précédent). Garde-fou contre la suppression accidentelle d'un dossier (voir question 2).
2. `read_sources` : pour chaque cible de `universe_targets` ayant un fichier, `storage.read_prices` ; les dix
   rapports `data/runs/YYYY-MM-DD.json` les plus récents, validés par `RunReport` ; tous les `data/signals/YYYY-MM-DD.json`
   (hors `latest.json`), validés par `SignalsFile`. Les fichiers dont le nom ne suit pas le motif sont ignorés.
   Tous les problèmes sont accumulés, puis `ExportSourceError` est levée s'il y en a.
3. `S = calendar.last_closed_session(now())`, `data_as_of = compute_data_as_of(...)`.
4. `render_files` : `tickers/{SYMBOL}.json` pour chaque symbole exporté, `overview.json`, `health.json`, puis
   `manifest.json` à partir des octets des autres fichiers.
5. `replace_dir` : `tempfile.mkdtemp(dir=out.parent, prefix=f".{out.name}.")`, écriture de tous les fichiers, puis
   `out` → `out.parent/.{out.name}.old-…`, temporaire → `out`, suppression de l'ancien. Toute exception supprime le
   temporaire et restaure `out` s'il avait déjà été déplacé.
6. CLI : en cas d'`ExportSourceError`, une ligne `chemin: raison` par fichier sur stderr et code 1. Sinon, résumé sur
   stdout (nombre de fichiers, taille totale, plus gros fichier, `data_as_of`) et code 0.

### Construction d'une fiche ticker
`close = np.asarray([bar[4] for bar in bars])` ; `sma(close, 20|50|200)`, `bollinger(close)` (seuls haut et bas sont
gardés), `rsi_wilder(close)`. Colonnes OHLC et volume recopiées depuis les barres (déjà arrondies à 4 décimales
par F01). Indicateurs de prix arrondis via `np.round(x, 4)`, RSI via `np.round(x, 2)`, `NaN` → `None`. `adj_close`
n'est pas exporté (R6).

## Traçabilité exigences → design → tests
| Exigence | Élément de design | Test(s) prévu(s) |
|---|---|---|
| R1 | `export()`, validation par `model_validate` à la construction ; aucune écriture hors `out` | `tests/export/test_dashboard.py::test_prices_only_repo_exports_m1_files` ; `::test_sources_untouched` (SHA-256 avant/après de `data/`) ; `tests/test_schemas.py::test_export_outputs_match_json_schemas` (`jsonschema` Draft 2020-12 sur chaque fichier produit) ; `pytest --disable-socket` |
| R2 | `replace_dir`, dossier temporaire voisin | `test_dashboard.py::test_stale_file_removed_after_export`, `::test_failure_during_write_keeps_previous_export` (monkeypatch d'une écriture qui lève), `::test_no_temp_dir_left_after_failure` |
| R3 | `ExportSourceError` / `ExportTargetError` / `ConfigError` → codes 1 / 2 / 2 ; résumé stdout | `tests/test_cli_export.py::test_corrupted_price_file_exits_1_and_names_file`, `::test_all_bad_sources_listed`, `::test_config_error_exits_2`, `::test_custom_out_and_data_dir`, `::test_summary_on_stdout` ; `test_dashboard.py::test_out_unchanged_when_source_invalid` |
| R4 | Modèles d'export et `SignalsFile` dans `schemas.py`, `SCHEMA_MODELS` étendu | `tests/test_schemas.py::test_generated_schemas_match_committed` (existant), `::test_ticker_series_lengths_must_match`, `::test_manifest_files_sorted_and_unique`, `::test_health_run_validate_alias_roundtrip`, `::test_export_floats_reject_nan` |
| R5 | `gen-types.mjs`, types commités, étape CI | CI : `npm run gen:types && git diff --exit-code -- src/types`, puis `npm run typecheck` ; vérification manuelle locale à la tâche concernée |
| R6 | `build_ticker` (colonnes, benchmark compris, sans milieu de Bollinger ni `adj_close`) | `test_build.py::test_ticker_columns_and_lengths`, `::test_benchmark_ticker_exported` ; `test_dashboard.py::test_prices_only_repo_exports_m1_files` |
| R7 | `indicators.sma`, `bollinger`, `rsi_wilder` | `tests/features/test_indicators.py::test_reference_values` (fixture tableur, 1e-4), `::test_bollinger_population_std`, `::test_rsi_flat_series_is_50`, `::test_rsi_strictly_increasing_is_100`, `::test_invalid_window_raises` |
| R8 | Fenêtres passées, `NaN` → `None`, `allow_inf_nan=False` | `test_indicators.py::test_warmup_lengths[sma20=19\|sma50=49\|sma200=199\|bb=19\|rsi=14]`, `::test_no_lookahead` (hypothesis, séries aléatoires et `t` quelconque), `::test_short_series_all_nan` ; `test_build.py::test_short_history_sma200_all_null`, `::test_no_nan_in_output` |
| R9 | `collect_markers`, lecture `data/signals/` | `test_build.py::test_markers_buy_sell_only_sorted`, `::test_markers_ignore_unexported_symbols` ; `test_dashboard.py::test_signals_fixture_markers_on_aapl`, `::test_no_signals_dir_empty_markers`, `::test_latest_json_not_read_as_marker` |
| R10 | `build_overview` | `test_build.py::test_overview_spark_60_values`, `::test_overview_short_history_spark`, `::test_change_1d`, `::test_change_1d_null_single_bar` |
| R11 | `build_manifest`, `digest`, `resolve_git_sha`, `compute_data_as_of` | `test_build.py::test_manifest_hashes_match_files`, `::test_manifest_excludes_itself`, `::test_benchmark_meta_name_symbol_sector_null`, `::test_data_as_of_is_min_last_date`, `::test_data_as_of_null_without_files` ; `test_dashboard.py::test_git_sha_from_env`, `::test_git_sha_null_outside_git` ; `test_cli_export.py::test_generated_at_uses_injected_clock` |
| R12 | `build_health` | `test_build.py::test_health_missing_file_ticker`, `::test_health_stale_boundary[S-3→false\|S-4→true]`, `::test_health_keeps_10_most_recent_runs_sorted`, `::test_health_summarises_last_execution_of_each_section`, `::test_health_quality_warnings_truncated_at_100` |
| R13 | `read_sources` : absent → vide, invalide → `ExportSourceError` | `test_dashboard.py::test_missing_optional_dirs_give_empty_sections`, `::test_invalid_signals_file_fails`, `::test_invalid_recent_run_report_fails`, `::test_orphan_price_file_not_exported` |
| R14 | Constantes d'arrondi, `rounded`, `render` | `test_build.py::test_rounding_grid` (parcours de chaque fichier : décimales par catégorie, NVDA 2010 à ~0,1 $ garde 4 décimales), `::test_render_is_minified_utf8`, `::test_schema_version_in_every_file` |
| R15 | Tris explicites, rendu canonique, horloge et `git_sha` injectés | `test_dashboard.py::test_two_exports_identical_bytes` |
| R16 | **M3** — esquisse : `build_overview` étendu (leaderboard, signaux enrichis), `ManifestStrategy` | **M3, à préciser** : `test_build.py::test_leaderboard_contains_all_baselines`, `::test_latest_signals_carry_model_and_perf` |
| R17 | **M3** — esquisse : `build_portfolio` s'appuyant sur `backtest/metrics.py` | **M3, à préciser** : `test_build.py::test_portfolio_metrics_equal_backtest_metrics`, `::test_model_switch_events_exported` |
| R18 | **M3** — esquisse : `build_models` (model cards, distribution, calibration) | **M3, à préciser** : `test_build.py::test_models_file_valid` |
| R19 | `tests/synthetic.py`, mesure du temps et des tailles | `test_dashboard.py::test_20_tickers_15_years_sizes_and_duration` (tailles § 7, durée < 30 s) ; partie M3 à ajouter |

## Dépendances ajoutées
| Paquet | Version | Justification |
|---|---|---|
| `numpy` | `>=2.5` (2.5.5 déjà dans `uv.lock`) | Indicateurs vectorisés (R7). Aujourd'hui dépendance transitive de pandas ; l'importer directement impose de la déclarer. Aucun nouveau paquet installé. |
| `hypothesis` (dev) | dernière stable | Test de propriété anti-look-ahead exigé par un critère d'acceptation (R8) ; déjà prévue par `02-architecture.md` (« Tests »). |
| `jsonschema` (dev) | dernière stable | Le critère d'acceptation R1 exige une validation par le JSON Schema (Draft 2020-12) en plus de pydantic. Tests uniquement : le code de production reste sans `jsonschema` (décision F02 Q1). |
| `json-schema-to-typescript` (devDependency du dashboard) | dernière stable, épinglée par `package-lock.json` | Types TS générés depuis `schemas/` (R5), outil déjà nommé par `03-data-contracts.md`. Utilisé seulement au développement et en CI, absent du bundle. |

## Risques & mitigations
- **Taille de `tickers/*.json` proche de la cible** : estimation ≈ 105 octets par séance × 3 780 ≈ 400 Ko pour 500 Ko
  autorisés. Le générateur synthétique écrit toujours 4 décimales (pire cas, les vrais cours sont plus courts).
  Si la cible est dépassée, s'arrêter et proposer une modification de spec (ex. dates en décalages de séances) plutôt
  qu'improviser.
- **Suppression accidentelle d'un dossier par `--out`** : la reconstruction complète (R2) supprime l'ancien dossier.
  Mitigation : `check_target` (question 2) et tests dédiés.
- **Remplacement non atomique sous Windows** : deux renommages successifs, et un dossier ouvert (serveur Vite, explorateur)
  peut bloquer le renommage (`PermissionError`). Mitigation : restauration de l'ancien dossier en cas d'échec, message
  explicite ; en CI (Linux, dossier neuf), aucun conflit.
- **RSI sensible à l'implémentation** : variantes Wilder / moyenne simple / EMA. Mitigation : définition exacte dans la
  spec (R7) et valeurs de référence calculées indépendamment au tableur (fixture figée).
- **Accumulation flottante dans les fenêtres** : `sliding_window_view(...).mean()` plutôt qu'une somme cumulée, pour
  éviter la dérive sur 3 780 valeurs ; tolérance de test 1e-4, cohérente avec l'arrondi de sortie.
- **Types TS générés et lint strict** : le code généré peut contenir des signatures d'index (`RunReport` accepte des clés
  supplémentaires) refusées par `strictTypeChecked`. Mitigation : `src/types/` exclu d'eslint mais couvert par `tsc`.
- **`SignalsFile` défini avant F07** : F07 pourrait vouloir le changer. Mitigation : modèle strictement conforme au
  contrat §4 ; toute modification future passera par la règle `schema_version` (question 1).
- **Rapport de run invalide** : un rapport récent corrompu bloquerait le déploiement (R13). Seuls les dix rapports lus sont
  validés : un vieux rapport cassé n'a pas d'effet (question 4).
- **Durée du test de performance en CI** : génération de ≈ 80 000 barres + export ; estimation < 10 s, seuil 30 s.

## ADR
Aucun ADR requis : `export/dashboard.py` et `features/indicators.py` sont déjà prévus par `02-architecture.md` ;
`export/build.py` en est une précision (comme `data/quality.py` pour F02). La génération de types commités suit le
même schéma que `schemas/` (fichiers générés + contrôle de synchronisation en CI).

## Décisions (validées le 2026-11-24)
1. **`SignalsFile` défini par F08** : `Signal` et `SignalsFile` ajoutés à `schemas.py` dès M1, strictement selon le
   contrat §4, avec `schemas/signals.schema.json` ; F07 les réutilisera.
2. **Garde-fou sur `--out`** : code 2 si le dossier est la racine du dépôt ou l'un de ses parents, égal à `data_root` ou
   le contenant, ou non vide sans `manifest.json`. Précision de R2/R3, sans modification de la spec.
3. **Dépendances de dev** : `hypothesis` et `jsonschema` ajoutées (exigées par les critères d'acceptation).
4. **Rapports de run** : seuls les dix plus récents sont lus et validés ; un rapport plus ancien et corrompu est ignoré.
5. **Types TS** : générés pour tous les schémas de `schemas/`, commités, exclus d'eslint, couverts par `tsc`.
6. **Découpage** : pur dans `export/build.py`, effets de bord dans `export/dashboard.py` ; `CLAUDE.md` mis à jour.
7. **Portée** : les tâches ne couvrent que les exigences `[M1]` ; ce plan sera complété pour M3 une fois les pré-requis
   de contrat réglés.

## Questions pour l'humain
Aucune pour M1.
