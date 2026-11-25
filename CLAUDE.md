# CLAUDE.md — TradingHelper

Outil d'aide au trading 100 % GitHub : Actions (ingestion yFinance, entraînement, paper trading) + Pages (dashboard).
Le projet est développé en **Spec-Driven Development (SDD)**. Lis ce fichier en entier avant toute tâche.

## Documents de référence (à lire selon la tâche)
- `specs/00-constitution.md` — principes non négociables. **Toujours** les respecter.
- `specs/01-vision.md` — périmètre v1 / hors périmètre.
- `specs/02-architecture.md` — stack, arborescence, abstraction `Strategy`, pièges GitHub.
- `specs/03-data-contracts.md` — formats JSON. Toute modif de contrat = modif de `schemas.py` + `th schemas` + `schema_version`.
- `specs/features/Fxx-*/spec.md` — exigences (R1…) et critères d'acceptation de chaque feature.
- `specs/roadmap.md` — ordre des features et statut.

## Workflow SDD (obligatoire)
1. **Spec** (`spec.md`) — le QUOI/POURQUOI. Rédigée/validée par l'humain. Ne jamais coder sans spec au statut ✅ Approved.
2. **Plan** (`plan.md`) — le COMMENT : fichiers touchés, signatures, choix techniques, risques. → `/spec-plan Fxx`
3. **Tasks** (`tasks.md`) — liste ordonnée de petites tâches (≤ ~1 h), chacune liée à des exigences `Rn`. → `/spec-tasks Fxx`
4. **Implement** — une tâche à la fois, tests d'abord. → `/spec-implement Fxx [Tn]`
5. **Verify** — chaque critère d'acceptation coché avec preuve (test, commande). → `/spec-verify Fxx`

Règles :
- Si l'implémentation révèle un problème dans la spec, **s'arrêter** et proposer une modification de spec, ne pas improviser.
- Une décision d'architecture non triviale → ADR dans `specs/adr/NNNN-titre.md` (template dans `specs/_templates/`).
- Mettre à jour le statut dans l'en-tête de la spec et dans `specs/roadmap.md`.
- Un commit = une tâche ; message `feat(F01): T3 incremental download (R1, R2)`.

## Commandes
```bash
uv sync                          # installer
uv run th --help                 # CLI du pipeline
uv run pytest                    # tests (aucun appel réseau autorisé)
uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/
uv run th schemas                # régénérer schemas/ depuis schemas.py
uv run th ingest                 # télécharger les cours (réseau) ; TH_DATA_DIR=<dossier> pour écrire ailleurs que data/
uv run th validate               # valider data/raw/prices/ (lecture seule) ; code 1 si règle bloquante violée
uv run th export [--out DIR]     # fichiers du dashboard (défaut dashboard/public/data/, reconstruit) ; code 1 si source invalide
uv run th commit-message --kind daily|backfill|model --since T0   # message de commit des workflows (sans config)
cd dashboard && npm run gen:types         # régénérer src/types/ depuis schemas/ (après `uv run th schemas`)
cd dashboard && npm ci && npm run dev     # dashboard local (après `uv run th export`)
cd dashboard && npm test                  # tests unitaires du dashboard (Vitest, src/lib/ et src/data/)
cd dashboard && npm run test:e2e          # tests e2e (Playwright, Chromium : `npx playwright install chromium`)
cd dashboard && npm run lighthouse        # mesure Lighthouse de l'Overview (vérification F09 R26, hors CI)
uv run python tests/dashboard_fixtures.py # régénérer dashboard/tests/fixtures/ (--check : vérifier)
```

## Conventions de code
- Python 3.12, typage complet, `from __future__ import annotations`, dataclasses/pydantic plutôt que dicts.
- Fonctions pures dans `features/`, `backtest/metrics.py`, `data/bars.py`, `data/quality.py` (règles de qualité), `export/build.py` (construction des fichiers du dashboard), `orchestration/commit_message.py` (message de commit des workflows), `dashboard/src/lib/` (formats, dates, routes, séries, marqueurs, thème) ; effets de bord (réseau, fichiers) isolés dans `data/source.py` (seul module qui importe yfinance/pandas), `data/storage.py`, `data/ingest.py`, `data/validate.py`, `export/dashboard.py`, `cli.py` ; côté dashboard, `dashboard/src/data/loader.ts` (seul module qui appelle `fetch`).
- Workflows GitHub Actions : logique de décision hors du YAML (commandes `th`, `scripts/ci/commit-and-push.sh`), structure vérifiée par `tests/test_workflows.py` ; actions tierces épinglées par SHA.
- Jamais d'appel réseau dans les tests : utiliser `FakePriceSource` et les fixtures de `tests/fixtures/`.
- Toute stochasticité passe par un `numpy.random.Generator` seedé reçu en paramètre.
- Écritures de fichiers de données : toujours atomiques via `storage` (`atomic_write_json` ; prix : `write_prices_if_changed`, sérialisation canonique `dumps_prices`).
- Dates : `datetime.date` pour les séances, UTC ISO-8601 pour les timestamps.
- Dashboard : TypeScript strict, types générés depuis `schemas/`, pas de framework lourd.
- Tests e2e du dashboard : données servies par interception depuis `dashboard/tests/fixtures/`, jamais depuis `public/data/` ; le graphique (canvas) se vérifie par ses attributs `data-*`.

## Interdits
- Pas de look-ahead (P1) : ne jamais accéder aux données au-delà de `ctx.date` dans une stratégie.
- Ne pas commiter `dashboard/public/data/`, features calculées, ni modèles > 2 Mo.
- Ne pas modifier à la main `data/raw/**` (sauf ADR) ni `schemas/*.json` (générés).
- Pas de passage d'ordre réel, pas de clé API de broker.
- Pas de nouvelle dépendance sans la justifier dans le `plan.md`.
