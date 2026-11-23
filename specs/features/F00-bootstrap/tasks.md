# Tâches — F00 Bootstrap du dépôt

> Généré par `/spec-tasks`. Chaque tâche est petite (≤ ~1 h), testable, et référence ses exigences.
> Ordre = ordre d'exécution. `[P]` = parallélisable avec la précédente.
> Prérequis local : Node 22 installé (décision 3 du plan).

## Python — squelette et hygiène

- [x] **T1** Squelette du package et `th version` — R1, R2, R3
  - Tests : `tests/test_cli.py::test_version_prints_package_version`, `::test_help_lists_commands` (écrits d'abord, via `typer.testing.CliRunner`)
  - Fichiers : `pyproject.toml` (layout src, backend `uv_build`, script `th`, `requires-python >=3.12`, `[dependency-groups] dev` avec ruff/mypy/pytest, config ruff/mypy/pytest), `uv.lock`, `.python-version`, `src/tradinghelper/__init__.py`, `src/tradinghelper/py.typed`, `src/tradinghelper/cli.py`, `tests/test_cli.py`, `.gitignore` minimal (`.venv/`, caches Python)
  - Fini quand : `uv run th version` affiche `tradinghelper 0.1.0` ; `uv lock --check` passe ; `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/ && uv run pytest` sortent en 0.

- [x] **T2** `.gitignore` complet et `.gitattributes` en LF — R18, R19, R1
  - Tests : `tests/test_repo_hygiene.py::test_gitignore_excludes[...]` (paramétré sur la liste R18, via `git check-ignore`), `::test_gitattributes_forces_lf[...]` (paramétré sur les extensions R19, via `git check-attr eol`), `::test_lockfiles_tracked` (`git ls-files uv.lock .python-version`)
  - Fichiers : `.gitignore`, `.gitattributes`, `tests/test_repo_hygiene.py` ; puis `git add --renormalize .`
  - Fini quand : les tests passent ; `git ls-files --eol` montre `i/lf` pour tous les fichiers suivis des extensions R19 ; `git status` ne montre plus d'avertissement CRLF.

- [x] **T3** Blocage réseau et dossier `research/` — R4, R5
  - Tests : `tests/test_repo_hygiene.py::test_network_is_blocked` (tente `socket.create_connection`, attend `SocketBlockedError`), `::test_src_never_imports_research` (scan AST de `src/`)
  - Fichiers : `pyproject.toml` (dev : `pytest-socket` ; `addopts = "--disable-socket"` ; exclusion `research/` pour ruff et mypy), `uv.lock`, `research/README.md`
  - Fini quand : les deux tests passent ; un fichier `.py` volontairement non conforme placé dans `research/` n'est pas signalé par ruff (vérifié puis supprimé).

## Python — configuration

- [x] **T4** Lecteur YAML strict et `ConfigError` — R8, R9
  - Tests : `tests/test_config.py::test_read_yaml_errors[...]` paramétré : fichier absent, fichier vide, YAML mal formé, clé dupliquée, racine non-mapping — chaque cas vérifie que `str(err)` contient le chemin du fichier
  - Fichiers : `src/tradinghelper/config.py` (`ConfigError`, `_read_yaml` avec `SafeLoader` rejetant les clés dupliquées), `pyproject.toml` (`pyyaml`, dev `types-PyYAML`), `uv.lock`, `tests/test_config.py`
  - Fini quand : tests verts sous `--disable-socket` ; `mypy --strict src/` passe.

- [x] **T5** Modèle `UniverseConfig` et ses règles — R6, R8
  - Tests : `tests/test_config.py::test_invalid_universe[...]` paramétré : clé inconnue, `tickers` vide, symbole dupliqué, symbole hors motif, `start` invalide, `start` future (avec `today` injecté), `currency` ≠ USD — chaque cas vérifie fichier **et** champ (ex. `tickers[3].symbol`) dans le message
  - Fichiers : `src/tradinghelper/config.py` (`_Strict`, `TickerConfig`, `UniverseConfig`, `_validate` qui convertit `ValidationError` en `ConfigError`), `tests/conftest.py` (fixture `write_config(tmp_path, **overrides)`), `pyproject.toml` (`pydantic`, plugin mypy pydantic), `uv.lock`
  - Fini quand : tests verts ; `mypy --strict src/` passe avec le plugin pydantic.

- [x] **T6** `BacktestConfig`, `StrategiesConfig`, `load_config` et YAML par défaut — R6, R8
  - Tests : `tests/test_config.py::test_default_config_loads` (vrai dossier `config/`, 20 tickers, SPY en benchmark), `::test_invalid_backtest[...]` (capital ≤ 0, commission < 0, slippage < 0), `::test_duplicate_strategy_id`
  - Fichiers : `src/tradinghelper/config.py` (`BacktestConfig`, `StrategyEntry`, `StrategiesConfig`, `AppConfig`, `load_config`), `config/universe.yaml` (annexe du plan), `config/backtest.yaml`, `config/strategies.yaml`
  - Fini quand : tests verts ; `load_config()` depuis la racine renvoie un `AppConfig` complet.

- [x] **T7** Résolution du dossier de config — R7
  - Tests : `tests/test_config.py::test_resolve_explicit_arg`, `::test_resolve_env_var` (via `monkeypatch.setenv("TH_CONFIG_DIR", …)`), `::test_resolve_from_subdirectory` (`monkeypatch.chdir` dans un sous-dossier d'un faux dépôt), `::test_no_repo_root_raises`
  - Fichiers : `src/tradinghelper/config.py` (`find_repo_root`, `resolve_config_dir`, branchement dans `load_config`)
  - Fini quand : tests verts ; `cd dashboard; uv run th version` fonctionne une fois T8 fait (vérifié en T8).

- [ ] **T8** Chargement de la config dans la CLI — R10, R2
  - Tests : `tests/test_cli.py::test_invalid_config_exits_2_without_traceback` (`TH_CONFIG_DIR` vers un dossier invalide : code 2, message sur stderr, pas de `Traceback`), `::test_help_works_without_valid_config`, `::test_version_from_subdirectory`
  - Fichiers : `src/tradinghelper/cli.py` (callback racine, `ctx.obj = AppConfig`, ensemble `CONFIG_EXEMPT_COMMANDS` vide)
  - Fini quand : tests verts ; `$env:TH_CONFIG_DIR="nope"; uv run th version` sort en 2 avec un message lisible.

## Dashboard

- [ ] **T9** [P] Scaffold Vite + TS strict + Preact + ESLint — R11
  - Tests : pas de logique à tester ; la vérification est faite par les scripts `lint`, `typecheck`, `build`
  - Fichiers : `dashboard/package.json` (scripts `dev`, `lint`, `typecheck`, `build`, `check:dist` ; `engines.node: ">=22 <23"`), `dashboard/package-lock.json`, `dashboard/.nvmrc`, `dashboard/tsconfig.json`, `dashboard/vite.config.ts`, `dashboard/eslint.config.js`, `dashboard/src/main.tsx`, `dashboard/src/App.tsx`, `dashboard/index.html` minimal
  - Fini quand : `cd dashboard; npm ci; npm run lint; npm run typecheck; npm run build` sortent en 0 avec Node 22 ; `tsconfig.json` contient `"strict": true`.

- [ ] **T10** Page « Hello TradingHelper » et bandeau P8 — R12, R13
  - Tests : `dashboard/scripts/check-dist.mjs` écrit d'abord (vérifie dans `dist/index.html` « Hello TradingHelper » et le texte exact de P8), doit échouer sur le build de T9
  - Fichiers : `dashboard/scripts/check-dist.mjs`, `dashboard/index.html` (titre, `<h1>`, bandeau statiques, `#app`), `dashboard/src/style.css`
  - Fini quand : `npm run build; npm run check:dist` passe sans `dashboard/public/data/` présent.

- [ ] **T11** `base` Vite configurable — R14
  - Tests : extension de `check-dist.mjs` : si `TH_DASHBOARD_BASE` est défini, tous les `src`/`href` d'assets de `dist/index.html` commencent par cette valeur (doit échouer avant la modification de `vite.config.ts`)
  - Fichiers : `dashboard/vite.config.ts`, `dashboard/scripts/check-dist.mjs`
  - Fini quand : `$env:TH_DASHBOARD_BASE="/TradingHelper/"; npm run build; npm run check:dist` passe, et le build sans la variable passe aussi.

## Documentation

- [ ] **T12** [P] README, LICENSE et tableau d'architecture — R20, R21, R6
  - Tests : `tests/test_repo_hygiene.py::test_readme_sections_and_disclaimer` (sections Installation, Commandes, Dashboard, texte exact P8), `::test_license_is_mit`
  - Fichiers : `README.md` (complété, pas écrasé ; inclut les réglages manuels GitHub de F10 R7), `LICENSE` (MIT, Gasthorn, 2026), `specs/02-architecture.md` (ligne Configuration : pydantic v2 + PyYAML ; backend `uv_build`)
  - Fini quand : tests verts ; le README cite les commandes `th` réellement disponibles (`th --help`, `th version`).

## CI

- [ ] **T13** Workflow `ci.yml` — R15, R16, R17, R3
  - Tests : `tests/test_repo_hygiene.py::test_ci_actions_pinned_by_sha`, `::test_ci_uses_no_secrets`, `::test_ci_declares_read_only_permissions`
  - Fichiers : `.github/workflows/ci.yml` (déclencheurs `push: main` + `pull_request` ; jobs `python` et `dashboard` ; `uv lock --check` + `uv sync --locked` ; `npm ci`, `lint`, `typecheck`, `build`, `check:dist`, puis 2ᵉ build avec `TH_DASHBOARD_BASE=/TradingHelper/` et `check:dist` ; caches uv/npm ; `concurrency` par ref ; `timeout-minutes: 10` ; SHA résolus via `gh api`, tag en commentaire)
  - Fini quand : tests verts ; après push de `feat/F00-bootstrap` (avec ton accord) et ouverture de la PR, les deux jobs sont verts.

## Vérification

- [ ] **T14** Vérification de tous les critères d'acceptation de la spec (→ `/spec-verify F00`) — R1–R21
  - Inclut les deux PR de test pour R15 (une avec une erreur ruff, une avec une erreur TS, sur des branches jetables fermées sans merge) et la vérification depuis un clone frais (R3).
  - Fini quand : chaque case de « Critères d'acceptation » est cochée avec sa preuve (commande, test ou lien de run).

## Couverture des exigences

| Exigence | Tâches |
|---|---|
| R1 | T1, T2 |
| R2 | T1, T8 |
| R3 | T1, T13 |
| R4 | T3 |
| R5 | T3 |
| R6 | T5, T6, T12 |
| R7 | T7 |
| R8 | T4, T5, T6 |
| R9 | T4 |
| R10 | T8 |
| R11 | T9 |
| R12 | T10 |
| R13 | T10 |
| R14 | T11 |
| R15 | T13 |
| R16 | T13 |
| R17 | T13 |
| R18 | T2 |
| R19 | T2 |
| R20 | T12 |
| R21 | T12 |

21/21 exigences couvertes ; T14 les revérifie toutes.
