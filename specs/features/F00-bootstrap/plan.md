# Plan — F00 Bootstrap du dépôt

> Généré par `/spec-plan`. À relire et valider avant `/spec-tasks`.

## Résumé de l'approche
Le dépôt ne contient aujourd'hui que des specs. F00 crée trois blocs indépendants :

1. **Package Python** `tradinghelper` (layout `src/`, backend `uv_build`), avec une CLI Typer minimale (`th version`) et un module `config` qui charge et valide les trois YAML. La config est chargée **dans le callback racine de Typer**, donc toute commande (y compris `th version`) échoue proprement (code 2) si la config est invalide ; `th --help` reste utilisable sans config.
2. **Dashboard** Vite + TypeScript strict + Preact. Le bandeau P8 et le titre « Hello TradingHelper » sont écrits **en HTML statique dans `index.html`** : ils s'affichent même si le JavaScript échoue, et sont vérifiables par un simple grep sur `dist/index.html`. Preact monte un composant `App` minimal dans `#app`.
3. **Hygiène du dépôt et CI** : `.gitignore`, `.gitattributes` (`eol=lf` + renormalisation), `LICENSE` MIT, `README.md` complété, `ci.yml` avec deux jobs (`python`, `dashboard`), actions épinglées par SHA.

Les tests Python sont 100 % hors réseau (`pytest-socket`). La date du jour utilisée par la validation est injectable pour garder les tests déterministes.

## Vérification constitution
| Principe | Impact | Comment il est respecté |
|---|---|---|
| P1 | Aucun | Pas de logique de décision dans F00. |
| P2 | Aucun | Pas de moteur dans F00. |
| P3 | Aucun | — |
| P4 | Fort | `uv.lock`, `package-lock.json`, `.python-version`, `.nvmrc` commités ; CI en `uv sync --locked` et `npm ci`. Version unique dans `pyproject.toml`. |
| P5 | Moyen | `.gitattributes` `eol=lf` pour JSON/YAML/Python/TS/MD/TOML → diffs stables sous Windows. `dashboard/public/data/` ignoré. Pas encore de JSON de données (schémas : F02). |
| P6 | Fort | CI sur `ubuntu-latest`, aucun secret, `timeout-minutes` par job (10 min), caches uv/npm. |
| P7 | Faible | La validation de config ne fait aucun appel réseau (R9). |
| P8 | Fort | Bandeau P8 en HTML statique dans `index.html`, texte exact vérifié dans `dist/` et dans le README. |
| P9 | Fort | `mypy --strict` (plugin pydantic), `ruff` lint + format, TS `strict`, ESLint ; `research/` exclu de ruff/mypy et test d'absence d'import. Seuil de couverture 90 % reporté à F04/F05 (hors périmètre de la spec). |

## Fichiers
| Fichier | Action | Rôle |
|---|---|---|
| `pyproject.toml` | créer | Métadonnées, `requires-python >=3.12`, script `th`, deps, `[dependency-groups] dev`, config ruff / mypy / pytest. |
| `uv.lock` | créer (généré) | Lockfile Python (P4). |
| `.python-version` | créer | `3.12`. |
| `src/tradinghelper/__init__.py` | créer | `__version__` lu via `importlib.metadata`. |
| `src/tradinghelper/py.typed` | créer | Marqueur PEP 561. |
| `src/tradinghelper/cli.py` | créer | App Typer `app`, callback racine (chargement config, gestion `ConfigError`), commande `version`. |
| `src/tradinghelper/config.py` | créer | Modèles pydantic, `ConfigError`, résolution du dossier, chargeur YAML strict, `load_config`. |
| `config/universe.yaml` | créer | 20 tickers par défaut + benchmark SPY (voir annexe). |
| `config/backtest.yaml` | créer | Clés minimales (capital, commissions, slippage). |
| `config/strategies.yaml` | créer | `strategies: []`. |
| `tests/__init__.py` | — | Non créé (tests en mode `importlib`). |
| `tests/conftest.py` | créer | Fixture `write_config(tmp_path, **overrides)` qui écrit un jeu de YAML valide modifiable. |
| `tests/test_cli.py` | créer | Tests `th version`, `th --help`, erreur de config → code 2. |
| `tests/test_config.py` | créer | Chargement par défaut, résolution du dossier, règles de validation paramétrées. |
| `tests/test_repo_hygiene.py` | créer | Socket bloqué, aucun import de `research`, `.gitignore`, `.gitattributes`, README. |
| `research/README.md` | créer | Rôle du dossier (explorations non importées). |
| `dashboard/package.json` | créer | Scripts `dev`, `lint`, `typecheck`, `build`, `check:dist` ; `engines.node`. |
| `dashboard/package-lock.json` | créer (généré) | Lockfile npm (P4). |
| `dashboard/.nvmrc` | créer | `22`. |
| `dashboard/tsconfig.json` | créer | `strict: true`, `jsx: react-jsx`, `jsxImportSource: preact`, `noEmit`. |
| `dashboard/vite.config.ts` | créer | Plugin Preact, `base` lu depuis `TH_DASHBOARD_BASE` (défaut `/`). |
| `dashboard/eslint.config.js` | créer | Flat config `@eslint/js` + `typescript-eslint` (recommended, type-aware). |
| `dashboard/index.html` | créer | `<title>`, bandeau P8 et `<h1>Hello TradingHelper</h1>` statiques, `<div id="app">`. |
| `dashboard/src/main.tsx` | créer | `render(<App />, #app)`. |
| `dashboard/src/App.tsx` | créer | Composant minimal (placeholder pour F09). |
| `dashboard/src/style.css` | créer | Style du bandeau (toujours visible). |
| `dashboard/scripts/check-dist.mjs` | créer | Vérifie `dist/index.html` : texte « Hello TradingHelper », texte exact P8, préfixe des assets égal à `TH_DASHBOARD_BASE`. |
| `.github/workflows/ci.yml` | créer | Jobs `python` et `dashboard` (R15–R17). |
| `.gitignore` | créer | Liste R18. |
| `.gitattributes` | modifier | Ajout `eol=lf` par extension (R19), puis `git add --renormalize .`. |
| `LICENSE` | créer | MIT, titulaire « Gasthorn », 2026. |
| `README.md` | modifier | Sections Installation, Commandes `th`, Dashboard, avertissement P8, réglages manuels GitHub (reprise de F10 R7 en avance). |
| `specs/02-architecture.md` | modifier | Tableau des choix : ligne « Configuration : pydantic v2 + PyYAML » et backend `uv_build`. |

## Interfaces / signatures
```python
# src/tradinghelper/config.py
from __future__ import annotations

SYMBOL_PATTERN = r"^[A-Z][A-Z0-9.\-]{0,9}$"
CONFIG_FILES = ("universe.yaml", "backtest.yaml", "strategies.yaml")

class ConfigError(Exception):
    """Erreur de configuration lisible : fichier + champ + raison."""
    def __init__(self, file: Path, field: str | None, reason: str) -> None: ...
    file: Path
    field: str | None
    reason: str
    # str(err) == "config/universe.yaml: tickers[3].symbol: symbole dupliqué 'AAPL'"

class _Strict(BaseModel):                     # base commune
    model_config = ConfigDict(extra="forbid", frozen=True)

class TickerConfig(_Strict):
    symbol: Annotated[str, StringConstraints(pattern=SYMBOL_PATTERN)]
    name: str
    sector: str
    start: date                               # validateur : <= today (lu dans le contexte de validation)

class UniverseConfig(_Strict):
    currency: Literal["USD"]
    benchmark: Annotated[str, StringConstraints(pattern=SYMBOL_PATTERN)]
    tickers: Annotated[list[TickerConfig], Field(min_length=1)]
    # validateur : unicité des symboles (casefold)

class BacktestConfig(_Strict):
    initial_capital: PositiveFloat
    commission_fixed: NonNegativeFloat
    commission_pct: NonNegativeFloat
    slippage_bps: NonNegativeFloat

class StrategyEntry(_Strict):
    id: str
    type: str
    active: bool = True
    params: dict[str, JsonValue] = Field(default_factory=dict)

class StrategiesConfig(_Strict):
    strategies: list[StrategyEntry]
    # validateur : unicité des id

class AppConfig(_Strict):
    config_dir: Path
    universe: UniverseConfig
    backtest: BacktestConfig
    strategies: StrategiesConfig

def find_repo_root(start: Path | None = None) -> Path:
    """Remonte depuis `start` (défaut : cwd) jusqu'au dossier contenant pyproject.toml. ConfigError sinon."""

def resolve_config_dir(config_dir: Path | None = None) -> Path:
    """argument > $TH_CONFIG_DIR > find_repo_root() / 'config'."""

def load_config(config_dir: Path | None = None, *, today: date | None = None) -> AppConfig:
    """Charge et valide les 3 fichiers. `today` injectable pour les tests (défaut : date.today())."""

# interne
def _read_yaml(path: Path) -> dict[str, object]:
    """PyYAML SafeLoader avec rejet des clés dupliquées ; ConfigError si absent, vide, mal formé ou non-mapping."""
def _validate[M: BaseModel](model: type[M], data: object, file: Path, today: date) -> M:
    """model_validate(..., context={'today': today}) ; convertit ValidationError -> ConfigError (1re erreur, loc jointe en 'a[0].b')."""
```

```python
# src/tradinghelper/cli.py
app = typer.Typer(no_args_is_help=True)

@app.callback()
def main(ctx: typer.Context) -> None:
    """Charge la config ; sur ConfigError : message sur stderr, typer.Exit(code=2)."""

@app.command()
def version() -> None:
    """Affiche 'tradinghelper X.Y.Z'."""
```

```ts
// dashboard/vite.config.ts
export default defineConfig({ base: process.env.TH_DASHBOARD_BASE ?? "/", plugins: [preact()] });
```

## Traçabilité exigences → design → tests
| Exigence | Élément de design | Test(s) prévu(s) |
|---|---|---|
| R1 | `pyproject.toml` (layout src, script `th`), `uv.lock`, `.python-version` | CI : `uv sync --locked` ; `tests/test_repo_hygiene.py::test_lockfiles_tracked` (`git ls-files`) ; `uv lock --check` en CI |
| R2 | `cli.version`, `__version__` via `importlib.metadata` | `tests/test_cli.py::test_version_prints_package_version`, `::test_help_lists_commands` |
| R3 | Config ruff/mypy/pytest dans `pyproject.toml` | Job CI `python` (4 commandes) ; `pytest` collecte ≥ 1 test |
| R4 | `addopts = "--disable-socket"` | `tests/test_repo_hygiene.py::test_network_is_blocked` |
| R5 | `research/README.md`, exclusions ruff/mypy | `tests/test_repo_hygiene.py::test_src_never_imports_research` (scan AST de `src/`) |
| R6 | Modèles pydantic, `load_config`, YAML par défaut | `tests/test_config.py::test_default_config_loads` (vrai dossier `config/`) |
| R7 | `resolve_config_dir`, `find_repo_root` | `tests/test_config.py::test_resolve_explicit_arg`, `::test_resolve_env_var`, `::test_resolve_from_subdirectory`, `::test_no_repo_root_raises` |
| R8 | `_read_yaml`, `_validate`, validateurs des modèles | `tests/test_config.py::test_invalid_config_raises[...]` paramétré : fichier absent, vide, YAML mal formé, clé YAML dupliquée, clé inconnue, `tickers` vide, symbole dupliqué (casse différente via `benchmark`/liste), symbole invalide, `start` future, `start` invalide, `currency` ≠ USD, capital ≤ 0, commission < 0, slippage < 0, id de stratégie dupliqué — chaque cas vérifie fichier + champ dans le message |
| R9 | Aucun import réseau dans `config.py` | Les tests de config tournent sous `--disable-socket` (R4) |
| R10 | Callback Typer → stderr + `Exit(2)` | `tests/test_cli.py::test_invalid_config_exits_2_without_traceback` (`CliRunner`, `TH_CONFIG_DIR` vers un dossier invalide, pas de `Traceback` dans la sortie) |
| R11 | `package.json`, `tsconfig.json`, `eslint.config.js`, `.nvmrc` | Job CI `dashboard` : `npm ci`, `lint`, `typecheck`, `build` |
| R12 | `index.html` statique | `npm run check:dist` (script `check-dist.mjs`) en CI |
| R13 | Aucun import de `public/data/` dans le code | Build CI exécuté sans `public/data/` (ignoré par git, donc absent en CI) |
| R14 | `base` lu depuis `TH_DASHBOARD_BASE` | CI : 2ᵉ build avec `TH_DASHBOARD_BASE=/TradingHelper/` puis `check:dist` qui vérifie le préfixe des assets |
| R15 | `ci.yml` (2 jobs, déclencheurs `push: main` + `pull_request`) | PR de test verte ; PR de test avec erreur ruff puis erreur TS → job rouge (vérification manuelle, preuve = liens des runs) |
| R16 | `permissions`, `concurrency`, `timeout-minutes`, SHA | Relecture ; `tests/test_repo_hygiene.py::test_ci_actions_pinned_by_sha` (regex `uses: .+@[0-9a-f]{40}`) |
| R17 | Aucun `secrets.*` dans `ci.yml` | `tests/test_repo_hygiene.py::test_ci_uses_no_secrets` |
| R18 | `.gitignore` | `tests/test_repo_hygiene.py::test_gitignore_excludes[...]` (`git check-ignore`) |
| R19 | `.gitattributes` + renormalisation | `tests/test_repo_hygiene.py::test_gitattributes_forces_lf` (`git check-attr eol`) |
| R20 | `README.md` | `tests/test_repo_hygiene.py::test_readme_sections_and_disclaimer` |
| R21 | `LICENSE` | `tests/test_repo_hygiene.py::test_license_is_mit` |

## Dépendances ajoutées
Versions : contrainte minimale dans `pyproject.toml` / `package.json`, version exacte figée par les lockfiles.

| Paquet | Version | Justification |
|---|---|---|
| `typer` | ≥ 0.15 | CLI `th` (choix d'architecture). |
| `pydantic` | ≥ 2.10 | Validation de la config, plus tard contrats JSON (`schemas.py`). |
| `pyyaml` | ≥ 6.0 | Lecture des YAML. Remplace `pydantic-settings` : on n'a pas besoin de surcharge par variables d'environnement, seulement d'un chargeur YAML strict. |
| `ruff` (dev) | ≥ 0.8 | Lint + format (P9). |
| `mypy` (dev) | ≥ 1.13 | Typage strict (P9). |
| `pytest` (dev) | ≥ 8.3 | Tests. |
| `pytest-socket` (dev) | ≥ 0.7 | Blocage du réseau dans les tests (R4). |
| `types-PyYAML` (dev) | ≥ 6.0 | Stubs pour `mypy --strict`. |
| `preact` | ≥ 10.25 | UI du dashboard (Q1). |
| `vite` (dev) | ≥ 6 | Build (choix d'architecture). |
| `@preact/preset-vite` (dev) | ≥ 2.9 | JSX Preact et alias pour Vite. |
| `typescript` (dev) | ≥ 5.6 | TS strict (P9). |
| `eslint`, `@eslint/js`, `typescript-eslint` (dev) | ≥ 9 / ≥ 9 / ≥ 8 | Lint du dashboard (R11). |

Pas de dépendance de test côté dashboard (pas de logique à tester en F00 ; `check-dist.mjs` n'utilise que Node).

## Risques & mitigations
- **Node local en v26 alors que la spec fixe 22 LTS** : `engines: { node: ">=22 <23" }` provoquera un avertissement `npm ci` en local (pas d'erreur, `engine-strict` non activé) ; risque de `package-lock.json` légèrement différent. → Utiliser Node 22 via `fnm`/`nvm-windows` en local, ou assouplir `engines` en `>=22` (voir questions).
- **Python local 3.15** : `.python-version` = 3.12 → `uv` télécharge un Python 3.12 géré. Aucun impact attendu.
- **Renormalisation LF** : `git add --renormalize .` après `.gitattributes` peut toucher tous les fichiers de specs → commit dédié, sans autre changement, pour garder un historique lisible.
- **`pytest-socket` sous Windows** : certains outils ouvrent des sockets locales (`socketpair`). Si un faux positif apparaît, ajouter `--allow-unix-socket` ou un marqueur ciblé, sans désactiver la règle globalement.
- **Callback Typer qui charge la config pour toute commande** : couplage voulu par R10, mais une future commande sans config (ex. `th schemas` en F02) devra pouvoir s'en dispenser → prévoir dès maintenant une liste de commandes exemptées dans le callback (vide en F00).
- **`start` comparée à `date.today()`** : dépend du fuseau de la machine ; acceptable pour une borne grossière, et `today` est injectable dans les tests.
- **Regex de symbole en majuscules** : la règle « doublon insensible à la casse » ne peut se déclencher que via la comparaison avec le `benchmark` ou après évolution de la regex ; le test de doublon se fera donc avec deux symboles identiques. Pas de modification de spec nécessaire.
- **SHA des actions** : à résoudre au moment de l'implémentation (`gh api repos/<owner>/<action>/commits/<tag>`), avec le tag en commentaire. Leur mise à jour n'est pas automatisée (voir questions).
- **PRs de test pour R15** : elles nécessitent un push sur GitHub ; à faire sur une branche jetable, fermée sans merge.

## ADR
Aucun ADR requis : les choix structurants (Preact, pydantic + PyYAML au lieu de pydantic-settings) sont tranchés et justifiés dans la spec F00. Le tableau de `02-architecture.md` sera mis à jour pour refléter le choix pydantic + PyYAML.

## Annexe — univers par défaut (Q2)
20 tickers, 10 secteurs GICS. `start: 2010-01-01` sauf META (introduction en bourse : `2012-05-18`).

| Secteur | Tickers |
|---|---|
| Information Technology | AAPL, MSFT, NVDA |
| Communication Services | GOOGL, META |
| Consumer Discretionary | AMZN, HD |
| Financials | JPM, V |
| Health Care | JNJ, UNH, LLY |
| Energy | XOM, CVX |
| Consumer Staples | PG, KO, WMT |
| Industrials | CAT |
| Utilities | NEE |
| Materials | LIN |

Benchmark : `SPY` (hors liste `tickers`).

## Décisions (validées le 2026-11-23)
1. Bandeau P8 et titre **en HTML statique** dans `index.html`.
2. Config **chargée dans le callback Typer** pour toute commande, avec une liste d'exemptions (vide en F00).
3. **Node 22 installé en local** (fnm ou nvm-windows) ; `engines` reste `>=22 <23`.
4. **Liste des 20 tickers** de l'annexe retenue telle quelle.
5. **Dependabot reporté** : hors périmètre de la spec F00, à ajouter au backlog (F10 ou tâche de maintenance).
6. Backend de build **`uv_build`**.

## Questions pour l'humain
Aucune.
