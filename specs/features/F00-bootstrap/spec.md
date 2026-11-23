# F00 — Bootstrap du dépôt

- **Statut** : 📝 Draft
- **Milestone** : M0
- **Dépend de** : —

## Objectif
Mettre en place le squelette Python + dashboard + CI pour que toutes les features suivantes s'y branchent.

## Exigences
- **R1** Le dépôt DOIT contenir un `pyproject.toml` géré par `uv`, package `tradinghelper` sous `src/`, Python ≥ 3.12.
- **R2** Le package DOIT exposer une CLI `th` (typer) avec une commande `th version`.
- **R3** `ruff check`, `ruff format --check`, `mypy --strict src/` et `pytest` DOIVENT passer sur un dépôt vierge.
- **R4** Le dossier `dashboard/` DOIT contenir une app Vite + TypeScript strict qui build (`npm run build`) une page « Hello TradingHelper » avec le bandeau d'avertissement (P8).
- **R5** `.github/workflows/ci.yml` DOIT s'exécuter sur `push` et `pull_request` : lint + typecheck + tests Python, puis lint + build du dashboard. Cache `uv` et `npm`.
- **R6** Les fichiers `config/universe.yaml`, `config/backtest.yaml`, `config/strategies.yaml` DOIVENT exister avec des valeurs par défaut et être chargés par `tradinghelper.config` (pydantic-settings), validés au chargement.
- **R7** `.gitignore` DOIT exclure `dashboard/public/data/`, `.venv/`, `node_modules/`, caches, `research/**/.ipynb_checkpoints`.
- **R8** Un `README.md` DOIT décrire installation locale, commandes `th`, et lien vers le dashboard.

## Critères d'acceptation
- [ ] `uv sync && uv run th version` affiche la version.
- [ ] `uv run pytest` passe (au moins un test de chargement de config).
- [ ] La CI est verte sur une PR.
- [ ] `cd dashboard && npm ci && npm run build` produit `dashboard/dist/index.html`.
- [ ] Une config invalide (ex. ticker dupliqué) lève une erreur explicite.

## Hors périmètre
Ingestion, déploiement Pages (F01, F10).
