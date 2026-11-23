# F00 — Bootstrap du dépôt

- **Statut** : ✔️ Done
- **Milestone** : M0
- **Dépend de** : —
- **Contrats** : `03-data-contracts.md` §1 (univers)
- **Principes clés** : P4 (lockfiles), P5 (diffs lisibles), P6 (CI frugale), P8 (avertissement), P9 (qualité)

## Objectif
Mettre en place le squelette Python + dashboard + CI pour que toutes les features suivantes s'y branchent,
avec des outils de qualité et une configuration validée dès le premier commit.

## User stories
- En tant qu'owner, je clone le dépôt et, avec `uv sync` et `npm ci`, j'obtiens un environnement qui passe lint, typage et tests.
- En tant qu'owner, si je fais une faute dans `config/*.yaml`, `th` refuse de démarrer avec un message qui indique le fichier, le champ et la raison.
- En tant que contributeur, toute PR qui casse le lint, le typage, les tests ou le build du dashboard est bloquée par la CI.

## Exigences

### Python
- **R1** `pyproject.toml` DOIT déclarer `requires-python = ">=3.12"`, le package `tradinghelper` sous `src/` (layout src) et le script `th = "tradinghelper.cli:app"`. `uv.lock` DOIT être commité et `uv lock --check` DOIT passer. Un fichier `.python-version` DOIT fixer `3.12` (version utilisée en CI).
- **R2** `th version` DOIT afficher `tradinghelper <X.Y.Z>`, où la version est lue via `importlib.metadata` (source unique : `pyproject.toml`), et sortir avec le code 0. `th --help` DOIT lister les commandes disponibles.
- **R3** Sur un clone frais, après `uv sync`, les commandes `ruff check .`, `ruff format --check .`, `mypy --strict src/` et `pytest` DOIVENT sortir avec le code 0, et `pytest` DOIT collecter au moins un test.
- **R4** Les tests NE DOIVENT PAS pouvoir ouvrir de connexion réseau : `pytest` DOIT être configuré avec `pytest-socket` (`--disable-socket`) par défaut.
- **R5** Le dossier `research/` DOIT exister (avec un `README.md` expliquant son rôle) et être exclu de ruff et de mypy ; aucun module de `src/` NE DOIT l'importer (P9).

### Configuration
- **R6** Les fichiers `config/universe.yaml`, `config/backtest.yaml` et `config/strategies.yaml` DOIVENT exister avec les valeurs par défaut décrites en annexe, et être chargés par `tradinghelper.config` (modèles pydantic v2 + PyYAML) via une fonction `load_config(config_dir: Path | None = None) -> AppConfig`.
- **R7** Le répertoire de config DOIT être résolu ainsi : argument explicite > variable d'environnement `TH_CONFIG_DIR` > `config/` à la racine du dépôt (dossier contenant `pyproject.toml`, recherché en remontant depuis le répertoire courant). Lancer `th` depuis un sous-dossier (ex. `dashboard/`) DOIT fonctionner.
- **R8** QUAND un fichier de config est invalide, le chargement DOIT lever une `ConfigError` dont le message contient le chemin du fichier, le champ concerné et la raison. Les règles minimales sont :
  - fichier absent, vide ou YAML mal formé ;
  - clé inconnue (`extra="forbid"` sur tous les modèles) ;
  - `tickers` vide ; symbole dupliqué (comparaison insensible à la casse) ; symbole hors du motif `^[A-Z][A-Z0-9.\-]{0,9}$` ;
  - `start` invalide ou postérieure à la date du jour ;
  - `currency` différente de `USD` (v1) ;
  - `initial_capital <= 0` ; commission ou slippage négatifs ;
  - `id` de stratégie dupliqué.
- **R9** La validation de la config NE DOIT faire aucun appel réseau (on ne vérifie pas l'existence d'un ticker chez yfinance).
- **R10** QUAND `th` rencontre une `ConfigError`, la CLI DOIT afficher le message sur stderr sans stacktrace et sortir avec le code 2.

### Dashboard
- **R11** `dashboard/` DOIT contenir une app Vite + TypeScript en Preact (Q1) avec `tsconfig.json` en `strict: true`. `package-lock.json` DOIT être commité. `package.json` DOIT exposer les scripts `lint` (ESLint + typescript-eslint), `typecheck` (`tsc --noEmit`) et `build`. La version de Node DOIT être fixée (`.nvmrc` + `engines`).
- **R12** `npm run build` DOIT produire `dashboard/dist/index.html` affichant « Hello TradingHelper » et le bandeau exact de P8 : « Outil expérimental et éducatif. Ceci n'est pas un conseil en investissement. »
- **R13** Le build DOIT réussir en l'absence de `dashboard/public/data/` (état normal avant F08).
- **R14** Le `base` Vite DOIT être configurable par variable d'environnement (défaut `/`, en production `/TradingHelper/`), en prévision de F09 R7.

### CI
- **R15** `.github/workflows/ci.yml` DOIT se déclencher sur `push` vers `main` et sur `pull_request`, avec deux jobs indépendants :
  - `python` : `uv sync --locked` → `ruff check` → `ruff format --check` → `mypy --strict src/` → `pytest` ;
  - `dashboard` : `npm ci` → `npm run lint` → `npm run typecheck` → `npm run build`.
  Cache `uv` et `npm` activés.
- **R16** `ci.yml` DOIT déclarer `permissions: { contents: read }`, une `concurrency` par ref avec `cancel-in-progress: true`, un `timeout-minutes` par job, et épingler toutes les actions tierces par SHA de commit (cohérent avec F10 R1, R5).
- **R17** La CI NE DOIT requérir aucun secret (P6) et DOIT donc fonctionner sur une PR provenant d'un fork.

### Dépôt
- **R18** `.gitignore` DOIT exclure au minimum : `dashboard/public/data/`, `dashboard/dist/`, `node_modules/`, `.venv/`, `__pycache__/`, `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`, `.coverage`, `htmlcov/`, `.env`, `research/**/.ipynb_checkpoints/`.
- **R19** `.gitattributes` DOIT imposer `eol=lf` pour `*.py`, `*.json`, `*.yaml`, `*.yml`, `*.ts`, `*.tsx`, `*.md`, `*.toml` afin que les diffs « une barre par ligne » (P5) et `ruff format --check` soient stables sous Windows.
- **R20** `README.md` (déjà présent, à compléter et non écraser) DOIT contenir les sections Installation, Commandes `th`, Dashboard (URL Pages prévue, mentionnée comme « active après F10 ») et le texte d'avertissement P8.
- **R21** Le dépôt DOIT contenir un fichier `LICENSE` MIT (Q5).

## Critères d'acceptation
- [x] `uv sync && uv run th version` affiche `tradinghelper <X.Y.Z>` et sort en 0. (R2)
- [x] `uv lock --check` passe et `git ls-files uv.lock .python-version` les retourne. (R1)
- [x] `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/ && uv run pytest` sortent en 0 sur un clone frais. (R3)
- [x] Un test qui tente `socket.create_connection` échoue avec `SocketBlockedError`. (R4)
- [x] Un test vérifie qu'aucun fichier de `src/` n'importe `research`. (R5)
- [x] Les trois fichiers de config par défaut se chargent sans erreur via `load_config()`. (R6)
- [x] Un test vérifie la résolution du dossier de config (argument, `TH_CONFIG_DIR`, remontée depuis un sous-dossier). (R7)
- [x] Un test paramétré couvre chaque règle de R8 et vérifie que le message contient fichier + champ. (R8)
- [x] Les tests de config passent avec le réseau bloqué. (R9)
- [x] `TH_CONFIG_DIR=<dossier invalide> uv run th version` sort en 2 sans stacktrace. (R10)
- [x] `cd dashboard && npm ci && npm run lint && npm run typecheck && npm run build` sort en 0. (R11)
- [x] `dashboard/dist/index.html` contient « Hello TradingHelper » et le texte exact de P8. (R12)
- [x] Le build passe sans `dashboard/public/data/`. (R13)
- [x] Un build avec la variable de `base` définie à `/TradingHelper/` produit des chemins d'assets préfixés. (R14)
- [x] La CI est verte sur une PR. (R15, R17)
- [x] Une PR de test avec une erreur ruff, puis une avec une erreur TS, fait échouer le job correspondant. (R15) — PR #2 : job `python` en échec à « Lint » (F401) ; PR #3 : job `dashboard` en échec à « Typage » (TS2322) ; l'autre job vert dans les deux cas.
- [x] Relecture de `ci.yml` : permissions, concurrency, timeouts, actions épinglées par SHA. (R16)
- [x] `git check-ignore dashboard/public/data/x.json dashboard/dist .venv node_modules .env` les retourne tous. (R18) — `node_modules/` est un motif de dossier : vérifié sur `dashboard/node_modules` et `node_modules/pkg/index.js`.
- [x] `git ls-files --eol` montre `i/lf` pour les types listés en R19. (R19)
- [x] Le README contient les sections attendues et le texte P8 (grep). (R20, R21)

## Hors périmètre
- Ingestion (F01), commande `th schemas` et vérification de `schemas/` en CI (F02 R6).
- Workflows `daily`, `deploy-pages`, `weekly-train`, `backfill`, test e2e smoke du dashboard (F10).
- Seuil de couverture ≥ 90 % sur `backtest/` et `strategies/` (P9) : installé avec F04/F05, quand ces paquets ont du code.
- Schéma complet de `backtest.yaml` et `strategies.yaml` : F00 pose des modèles minimaux, étendus par F04, F05 et F06.
- Génération des types TS depuis `schemas/` (F08).

## Annexe — valeurs par défaut

`config/universe.yaml` (liste : Q2) :
```yaml
currency: USD
benchmark: SPY          # ingéré comme un ticker à part, hors univers de trading (Q3)
tickers:
  - { symbol: AAPL, name: Apple Inc., sector: Technology, start: 2010-01-01 }
  # … ~20 tickers US
```

`config/backtest.yaml` (clés minimales, sémantique définie par F04 R3) :
```yaml
initial_capital: 10000.0
commission_fixed: 1.0     # USD par ordre
commission_pct: 0.0       # fraction du notionnel
slippage_bps: 5
```

`config/strategies.yaml` (structure minimale, entrées ajoutées par F05/F06) :
```yaml
strategies: []            # chaque entrée : { id, type, active, params }
```

## Dépendances introduites (à justifier dans `plan.md`)
`typer`, `pydantic`, `pyyaml` (runtime) ; `ruff`, `mypy`, `pytest`, `pytest-socket`, `types-PyYAML` (dev) ;
`vite`, `typescript`, `eslint`, `typescript-eslint` (dashboard).

## Décisions (validées le 2026-11-23)
- **Q1** Dashboard : **Preact** (composants pour F09, ~4 Ko).
- **Q2** Tickers par défaut : **20 grandes capitalisations du S&P 500 réparties sur ≥ 8 secteurs** (liste fixée dans `plan.md`).
- **Q3** Benchmark SPY : **ingéré comme ticker de référence, jamais tradé** (modalités d'ingestion dans F01).
- **Q4** Node : **22 LTS**.
- **Q5** Licence : **MIT**.
- **Q6** `th version` : **sans SHA git** ; le SHA est capturé par les model cards (F06).

## Questions ouvertes
Aucune.
