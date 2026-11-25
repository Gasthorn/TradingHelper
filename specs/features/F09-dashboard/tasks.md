# Tâches — F09 Dashboard GitHub Pages (M1)

> Généré par `/spec-tasks`. Chaque tâche est petite (≤ ~1 h), testable, et référence ses exigences.
> Ordre = ordre d'exécution. `[P]` = parallélisable avec la précédente.
> **Portée M1** (décision 4 du plan) : R13 et R18 ne sont couvertes que pour leur état vide M1 ; R19–R22 seront découpées
> après complément du plan (formats `portfolios/*` et `models.json` fixés dans F08).
> Aucun test ne fait d'appel réseau : `pytest` tourne sous `--disable-socket`, Playwright sert les données par
> interception (`**/data/**`) depuis `dashboard/tests/fixtures/`. Seule T26 utilise des données réelles, en manuel.
> « Qualité verte » = `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/ && uv run pytest` sortent en 0.
> « Qualité dashboard verte » = `npm run lint && npm run typecheck && npm test && npm run build && npm run check:dist`
> sortent en 0 (dans `dashboard/` ; `npm test` existe à partir de T1).
> « E2e vert » = `npm run test:e2e` sort en 0 (à partir de T10).

## Logique pure (`dashboard/src/lib/`, Vitest)

- [x] **T1** Vitest et URL des données — R23, R2, R10
  - Tests : `src/lib/urls.test.ts` : `dataUrl` (`${base}data/${path}?v=${sha256}`), base `/` et `/TradingHelper/`,
    chemin imbriqué `tickers/AAPL.json`, `MANIFEST_PATH`.
  - Fichiers : `dashboard/package.json` (devDependency `vitest`, script `test`), `package-lock.json`,
    `dashboard/vite.config.ts` (section `test` : environnement `node`, `src/**/*.test.ts` ; deux projets Vitest dont le
    fichier de setup fixe `process.env.TZ` à `America/Los_Angeles` puis `Pacific/Auckland`), `dashboard/tsconfig.json`
    (types `vitest`), `dashboard/src/lib/urls.ts`.
  - Fini quand : `npm test` exécute les tests sous les deux fuseaux et sort en 0 ; qualité dashboard verte.
  - Fait (2026-11-25) : `vitest` 5.1.2 ; fuseau passé par `test.env.TZ` de chaque projet (pas de fichier de setup),
    vérifié par `urls.test.ts` ; `tsconfig.json` inchangé (imports explicites depuis `vitest`, pas de globales).
    12 tests (6 × 2 fuseaux).

- [x] **T2** [P] Formats `fr-FR` — R11, R8
  - Tests : `src/lib/format.test.ts` : `232,40 $`, `0,1234 $` (prix < 1), `1 234,56 $` (séparateur de milliers
    normalisé en espace insécable, vérifié explicitement), `+0,63 %`, `−1,20 %`, `67 %`, `23/11/2026`, `null` → `—`
    pour chaque fonction ; flèche ▲/▼ et signe d'une variation (`changeParts`).
  - Fichiers : `dashboard/src/lib/format.ts`, `dashboard/src/lib/format.test.ts`.
  - Fini quand : tests verts sous les deux fuseaux ; qualité dashboard verte.
  - Fait (2026-11-25) : séparateurs fixés dans le code, pas par `Intl` (sortie variable selon ICU, « $US » pour le
    dollar) : milliers U+202F, avant `$`/`%` U+00A0, moins U+2212 ; aucun signe pour une valeur arrondie à zéro ;
    valeur non finie → « — ». 44 tests (22 × 2 fuseaux).

- [x] **T3** Dates civiles et fraîcheur — R6, R11
  - Tests : `src/lib/dates.test.ts` : `dayNumber`/`fromDayNumber` aller-retour (y compris 29 février) ;
    `todayInNewYork` (instant 2026-11-24T03:00Z → `2026-11-23`) ; `lastAssumedSession` (lundi → vendredi précédent,
    samedi → vendredi) ; `sessionsBehind` (même semaine, à cheval sur un week-end, férié compté comme séance,
    `d >= S'` → 0) ; `freshness` (`null` → `none`, retard 3 → `fresh`, 4 → `stale`) ; une date de séance n'est jamais
    décalée sous les deux fuseaux de test.
  - Fichiers : `dashboard/src/lib/dates.ts` (sans `periodStart`, en T4), `dashboard/src/lib/dates.test.ts`.
  - Fini quand : tests verts sous les deux fuseaux ; `dates.ts` n'appelle jamais `new Date("YYYY-MM-DD")`
    (test `dates.test.ts::no_string_date_parsing` sur le source) ; qualité dashboard verte.
  - Fait (2026-11-25) : retard calculé par formule (jours ouvrés avant un numéro de jour), sans boucle ; contrôle
    du source par import `?raw`, commentaires retirés avant analyse ; `dayNumber` refuse une date mal formée ou
    inexistante (`RangeError`). 54 tests (27 × 2 fuseaux).

- [x] **T4** Périodes et séries — R16, R15
  - Tests : `dates.test.ts::periodStart` (1M depuis le 2026-11-23 → 2026-10-23 ; depuis le 31 mars → 28/29 février ;
    1A, 5A ; Max → `null`) ; `src/lib/series.test.ts` : `periodWindow` (fenêtre exacte, historique plus court que la
    période → série complète, Max), `linePoints` (exclut les `null`, respecte la fenêtre), `isAllNull`.
  - Fichiers : `dashboard/src/lib/dates.ts` (`Period`, `periodStart`), `dashboard/src/lib/series.ts`,
    `dashboard/src/lib/series.test.ts`.
  - Fini quand : tests verts ; qualité dashboard verte.
  - Fait (2026-11-25) : `periodStart` en arithmétique de mois (jour borné à la fin du mois), `PERIODS` exporté
    pour le sélecteur ; `periodWindow` par recherche dichotomique (ordre lexical des dates) ; série vide → fenêtre
    `{ from: 0, to: -1 }`. 34 tests ajoutés (17 × 2 fuseaux).

- [x] **T5** [P] Routes — R1, R14
  - Tests : `src/lib/routes.test.ts` : `#/`, `''`, `#` → overview ; `#/ticker/AAPL` ; `#/ticker/brk.b` → `BRK.B` ;
    `#/ticker/BRK%2DB` → `BRK-B` ; encodage invalide (`%E0%A4%A`) → `not_found` ; `#/ticker/` vide, `#/inconnu`,
    `#/portfolios`, `#/portfolio/x`, `#/models`, `#/health` → `not_found` (non livrées en M1) ; barre finale tolérée.
  - Fichiers : `dashboard/src/lib/routes.ts`, `dashboard/src/lib/routes.test.ts`.
  - Fini quand : tests verts ; qualité dashboard verte.
  - Fait (2026-11-25) : `parseHash` ne lève jamais (encodage invalide → `not_found`) ; noms de route sensibles à la
    casse, symbole mis en majuscules ; ajout de `tickerHash` (lien Overview → fiche, aller-retour testé).
    40 tests (20 × 2 fuseaux).

- [x] **T6** [P] Marqueurs et enrichissement P8 — R17
  - Tests : `src/lib/markers.test.ts` : `strategyOptions` (uniques, triées, vide → `[]`) ; `visibleMarkers` filtre par
    stratégie, exclut les dates absentes de la série sans erreur, ajoute `modelId`/`sharpeOos` depuis
    `manifest.strategies`, `known: false` et valeurs `null` pour une stratégie inconnue ; ordre conservé (date puis
    stratégie).
  - Fichiers : `dashboard/src/lib/markers.ts`, `dashboard/src/lib/markers.test.ts`.
  - Fini quand : tests verts ; qualité dashboard verte.
  - Fait (2026-11-25) : stratégie `null` = toutes ; entrées non modifiées (test). 18 tests (9 × 2 fuseaux).

- [x] **T7** [P] Préférence de thème — R7
  - Tests : `src/lib/theme.test.ts` : `parsePreference` (`light`, `dark`, `system`, `null`, valeur inconnue → `system`) ;
    `resolveTheme` (4 combinaisons + `system`) ; `THEME_KEY` stable.
  - Fichiers : `dashboard/src/lib/theme.ts`, `dashboard/src/lib/theme.test.ts`.
  - Fini quand : tests verts ; qualité dashboard verte.
  - Fait (2026-11-25) : ajout de `THEME_PREFERENCES` et `nextPreference` (ordre de la bascule système → clair →
    sombre). 32 tests (16 × 2 fuseaux).

- [x] **T8** Chargeur de données — R2, R3
  - Tests : `src/data/loader.test.ts` (fetch injecté) : manifest demandé avec `cache: "no-cache"` ; fichier demandé à
    l'URL `?v=` du manifest ; deuxième `loadFile` du même chemin sans nouvel appel ; `DataError` `missing` (HTTP 404,
    chemin absent de `manifest.files`), `invalid_json`, `schema_version` (valeur 2) avec `path` renseigné.
  - Fichiers : `dashboard/src/data/loader.ts`, `dashboard/src/data/loader.test.ts`, `dashboard/vite.config.ts`
    (inclure `src/data/**/*.test.ts`).
  - Fini quand : tests verts ; qualité dashboard verte.
  - Fait (2026-11-25) : fabrique `createDataLoader(base, fetchFn)` (cache isolé par test) + instance `dataLoader`
    de l'application, au lieu de fonctions libres ; échec réseau classé `missing` ; une erreur n'est pas mise en
    cache (réessai possible). `vite.config.ts` inchangé (`src/**/*.test.ts` couvre déjà `src/data/`).
    34 tests (17 × 2 fuseaux).

## Fixtures d'export

- [x] **T9** Fixtures `empty`, `m1`, `m1-signals` — R24
  - Tests : `tests/test_dashboard_fixtures.py::test_fixtures_up_to_date[empty|m1|m1-signals]` (régénération dans
    `tmp_path` identique octet pour octet au dossier commité ; message d'échec donnant la commande de régénération),
    `::test_fixtures_match_json_schemas` (chaque fichier validé par son `schemas/*.schema.json`, Draft 2020-12),
    `::test_m1_fixture_content` (AAPL contient le 2026-11-19, le 2026-11-20 et le 2026-11-23 ; BRK.B a `sma200`
    entièrement `null` ; NVDA a un cours < 1 $ ; SPY est le benchmark), `::test_empty_fixture_has_no_data`
    (`data_as_of: null`, aucun `tickers/`), `::test_m1_signals_markers` (BUY 20/11 et SELL 23/11 sur AAPL).
  - Fichiers : `tests/dashboard_fixtures.py` (univers dédié AAPL, BRK.B, NVDA + benchmark SPY ; prix synthétiques
    seedés via `tests/synthetic.py` ; rapports et signaux de `tests/fixtures/export/` ; `export()` de F08 avec
    `FROZEN_NOW` et `FROZEN_SHA` ; `python -m tests.dashboard_fixtures [--check]`),
    `tests/test_dashboard_fixtures.py`, `dashboard/tests/fixtures/{empty,m1,m1-signals}/` (générés).
  - Fini quand : tests verts ; régénérer deux fois ne produit aucun diff git ; qualité verte.
  - Fait (2026-11-25) : rendu par `render_files` (pur) puis `replace_dir` de F08, plutôt que `export()` (pas de
    config ni de dossier de données à préparer) ; commande `uv run python tests/dashboard_fixtures.py [--check]`
    (le dossier `tests/` n'est pas un paquet : `-m tests.dashboard_fixtures` impossible) ; seed 9, horloge
    2026-11-23T22:50Z. 17 fichiers, 243 Ko ; `--check` sort en 0 après régénération. 9 tests.

## Tests de bout en bout et coque de l'application

- [ ] **T10** Infrastructure Playwright — R25, R5
  - Tests : `e2e/disclaimer.spec.ts::exact P8 text on home` (sur la page actuelle) ; `e2e/support.spec.ts` :
    `useFixture` sert `dashboard/tests/fixtures/m1/manifest.json` à `<base>data/manifest.json` ; `failFile` renvoie 404
    ou du JSON invalide ; la collecte d'erreurs console fait échouer un test qui déclenche `console.error`.
  - Fichiers : `dashboard/package.json` (devDependency `@playwright/test`, script `test:e2e` qui construit `dist/` et
    `dist-base/` puis lance Playwright), `package-lock.json`, `dashboard/playwright.config.ts` (Chromium ; serveurs
    `vite preview` sur 4173 base `/` et 4174 base `/TradingHelper/` ; projets `desktop` et `mobile` 375 × 812),
    `dashboard/e2e/support.ts`, `dashboard/e2e/disclaimer.spec.ts`, `dashboard/e2e/support.spec.ts`,
    `dashboard/tsconfig.json` (inclure `e2e/`, `playwright.config.ts`), `dashboard/eslint.config.js` (ignorer
    `test-results/`, `playwright-report/`, `dist-*/`), `.gitignore` (mêmes dossiers sous `dashboard/`).
  - Fini quand : e2e vert en local ; `git check-ignore dashboard/test-results dashboard/dist-base` les retourne ;
    qualité dashboard verte.

- [ ] **T11** Coque : titre, routeur, page introuvable, en-tête — R1, R5, R10
  - Tests : `e2e/routing.spec.ts::deep link reload` (`#/ticker/AAPL` rechargé → page Ticker, encore vide), `::unknown
    route` et `::portfolios not delivered` (« Page introuvable » + lien vers `#/`) ; `e2e/disclaimer.spec.ts` étendu :
    texte exact sur `#/`, `#/ticker/AAPL`, `#/inconnu` ; `npm run check:dist` exige le titre « TradingHelper ».
  - Fichiers : `dashboard/index.html` (titre « TradingHelper », bandeau statique conservé, en-tête retiré du HTML),
    `dashboard/src/main.tsx`, `dashboard/src/App.tsx`, `dashboard/src/hooks/useRoute.ts`,
    `dashboard/src/pages/NotFound.tsx`, `dashboard/src/components/Header.tsx` (titre, navigation),
    `dashboard/scripts/check-dist.mjs`, `specs/features/F00-bootstrap/spec.md` (R12 et son critère : « TradingHelper »,
    décision 1 du plan), `dashboard/src/style.css`.
  - Fini quand : e2e vert ; tous les liens passent par `BASE_URL` ou par un hash ; qualité dashboard verte.

- [ ] **T12** États de chargement, d'erreur et vide — R3, R4
  - Tests : `e2e/errors.spec.ts::manifest missing`, `::overview 404`, `::invalid json`, `::schema_version 2` (message
    nommant le fichier, bandeau et navigation visibles, aucune `pageerror`) ; `e2e/empty.spec.ts::empty fixture no
    data` (« Aucune donnée disponible »).
  - Fichiers : `dashboard/src/data/useData.ts`, `dashboard/src/components/ErrorPanel.tsx`,
    `dashboard/src/components/EmptyState.tsx`, `dashboard/src/components/ErrorBoundary.tsx` (limite d'erreur par page,
    plan « Risques »), `dashboard/src/App.tsx` (chargement du manifest), `dashboard/src/pages/Overview.tsx` (squelette :
    états chargement / erreur / aucune donnée).
  - Fini quand : e2e vert ; qualité dashboard verte.

- [ ] **T13** Date des données et alerte de fraîcheur — R6
  - Tests : `e2e/freshness.spec.ts` (`page.clock` figée, fixture `m1` à `data_as_of` 2026-11-23) : `::date shown on
    every route` (`23/11/2026` sur `#/`, `#/ticker/AAPL`, `#/inconnu`), `::+3 sessions fresh` (horloge au 2026-11-27,
    New York), `::+4 sessions stale` (horloge au 2026-11-30 → « Données périmées (4 séances) »), `::empty fixture`
    (aucune alerte, « Aucune donnée disponible »).
  - Fichiers : `dashboard/src/components/Header.tsx` (date et badge via `lib/dates.ts::freshness`).
  - Fini quand : e2e vert ; qualité dashboard verte.

- [ ] **T14** Thème et contrastes — R7, R8
  - Tests : `e2e/theme.spec.ts::toggle without reload` (couleur de fond calculée change), `::persists after reload`,
    `::system follows emulated scheme` (`page.emulateMedia({ colorScheme })`), `::no flash` (`data-theme` posé avant le
    chargement du bundle) ; `e2e/a11y.spec.ts::no contrast violation light|dark` (`@axe-core/playwright`, règle
    `color-contrast`, sur `#/` et `#/inconnu`) ; `::focus visible` (contour visible au clavier sur la bascule).
  - Fichiers : `dashboard/index.html` (script inline de thème), `dashboard/src/hooks/useTheme.ts`,
    `dashboard/src/components/Header.tsx` (bascule à trois états), `dashboard/src/style.css` (variables clair/sombre,
    couleurs haussier/baissier, focus), `dashboard/package.json` (devDependency `@axe-core/playwright`),
    `package-lock.json`, `dashboard/e2e/a11y.spec.ts`, `dashboard/e2e/theme.spec.ts`.
  - Fini quand : e2e vert ; qualité dashboard verte.

## Overview

- [ ] **T15** Page Overview — R12, R4, R13 (état vide M1), R2, R8
  - Tests : `e2e/overview.spec.ts::one row per symbol with sparkline` (4 lignes dans l'ordre du manifest, un `<svg>` par
    ligne, cours et variation formatés), `::benchmark flagged` (SPY « indice de référence »), `::row links to ticker`,
    `::change has sign and arrow` ; `e2e/empty.spec.ts::m1 sections empty` (KPIs, leaderboard et derniers signaux en
    état vide) ; `e2e/loading.spec.ts::overview loads only manifest and overview` (aucune requête `tickers/*`).
  - Fichiers : `dashboard/src/pages/Overview.tsx`, `dashboard/src/components/Sparkline.tsx`,
    `dashboard/src/components/Change.tsx`, `dashboard/src/components/ScrollTable.tsx`, `dashboard/src/style.css`.
  - Fini quand : e2e vert ; axe (T14) toujours sans violation sur `#/` avec données ; qualité dashboard verte.

## Ticker

- [ ] **T16** Page Ticker sans graphique : symbole, sélecteurs, fiche vide — R14, R16, R4, R18 (état vide M1)
  - Tests : `e2e/ticker.spec.ts::brk.b case-insensitive` (`#/ticker/brk.b` → titre `BRK.B`), `::unknown symbol message`
    (`#/ticker/ZZZ` → « Pas de données pour ZZZ », aucune requête `tickers/ZZZ.json`), `::default period 6M`
    (sélecteur), `::strategy selector hidden` (fixture `m1`), `::signal card empty` (« Aucun signal pour l'instant »).
  - Fichiers : `dashboard/src/pages/Ticker.tsx` (résolution, chargement de `tickers/{SYMBOL}.json`, sélecteurs de
    période, d'overlays et de stratégie, emplacement du graphique, légende, fiche signal vide).
  - Fini quand : e2e vert ; qualité dashboard verte.

- [ ] **T17** Graphique de prix (`lightweight-charts`) — R15, R16, R2, R8
  - Tests : `e2e/ticker.spec.ts::chart renders` (`data-bars` = nombre de barres de la période 6M), `::1M first bar`
    (`data-first-date` ≥ 2026-10-23), `::default overlays` (`data-overlays="sma20,sma50"`), `::toggle bollinger`,
    `::sma200 disabled short history` (BRK.B : case désactivée, mention « historique insuffisant »), `::hollow up candles`
    (`data-up-style="hollow"`), `::rsi pane with 30/70` ; `e2e/loading.spec.ts::chart chunk only on ticker` (le chunk
    `lightweight-charts` n'est demandé ni sur `#/` ni sur `#/inconnu`).
  - Fichiers : `dashboard/package.json` (dépendance `lightweight-charts`), `package-lock.json`,
    `dashboard/src/charts/priceChart.ts` (`createPriceChart`, état exposé en `data-*`, décision 3 du plan),
    `dashboard/src/pages/Ticker.tsx` (`import()` dynamique, `setData`, `setOverlays`).
  - Fini quand : e2e vert ; `npm run build` produit un chunk séparé contenant `lightweight-charts` ; l'attribution
    TradingView est conservée ; qualité dashboard verte.

- [ ] **T18** Marqueurs et détail P8 — R17, R8
  - Tests : `e2e/ticker.spec.ts::m1-signals markers` (fixture `m1-signals`, AAPL : `data-markers="2"`, légende listant
    BUY ▲ le 20/11/2026 et SELL ▼ le 23/11/2026 avec leur confiance, rien le 19/11), `::marker detail P8` (stratégie,
    confiance, modèle et `sharpe_oos` affichés, « — » pour une stratégie absente du manifest), `::strategy selector
    filters` (sélecteur visible, filtrage effectif), `::marker outside series ignored` (fixture modifiée par interception
    : marqueur à une date absente → non tracé, aucune erreur console).
  - Fichiers : `dashboard/src/charts/priceChart.ts` (`setMarkers` : `arrowUp`/`belowBar` « BUY »,
    `arrowDown`/`aboveBar` « SELL »), `dashboard/src/pages/Ticker.tsx` (sélecteur de stratégie, liste des marqueurs
    visibles accessible au clavier).
  - Fini quand : e2e vert ; qualité dashboard verte.

- [ ] **T19** [P] Thème du graphique — R7
  - Tests : `e2e/theme.spec.ts::chart follows theme` (sur `#/ticker/AAPL`, `data-theme` du graphique et couleur de fond
    du canvas changent à la bascule, sans rechargement ni recréation du graphique).
  - Fichiers : `dashboard/src/charts/priceChart.ts` (`setTheme`, couleurs lues dans les variables CSS),
    `dashboard/src/pages/Ticker.tsx` (abonnement au thème).
  - Fini quand : e2e vert ; axe sans violation sur `#/ticker/AAPL` dans les deux thèmes ; qualité dashboard verte.

## Exigences transverses

- [ ] **T20** Mobile 375 px et clavier — R9, R8
  - Tests : `e2e/mobile.spec.ts` (projet `mobile`) : `::no horizontal scroll` (`scrollWidth <= 375` sur `#/`,
    `#/ticker/AAPL`, `#/ticker/BRK.B`, `#/inconnu`, page d'erreur), `::touch targets 44px` (boutons, liens de
    navigation, sélecteurs) ; `e2e/a11y.spec.ts::keyboard reaches period selector` (tabulation depuis le début de page
    jusqu'au sélecteur de période, puis activation de 1M au clavier).
  - Fichiers : `dashboard/src/style.css`, ajustements ciblés dans `pages/` et `components/` si un test échoue.
  - Fini quand : e2e vert sur les projets `desktop` et `mobile` ; qualité dashboard verte.

- [ ] **T21** [P] Déploiement sous `/TradingHelper/` — R10
  - Tests : `e2e/base.spec.ts` (serveur 4174) : `::overview loads under base`, `::ticker loads under base`,
    `::no request outside base` (toutes les requêtes de même origine commencent par `/TradingHelper/`).
  - Fichiers : `dashboard/e2e/base.spec.ts` ; corrections dans `src/` si une URL ignore `BASE_URL`.
  - Fini quand : e2e vert ; qualité dashboard verte.

- [ ] **T22** [P] Requêtes de données — R2
  - Tests : `e2e/loading.spec.ts::urls carry manifest hash` (chaque requête de données hors manifest porte `?v=` égal au
    `sha256` du manifest), `::manifest no-cache` (en-tête de requête `cache-control: no-cache` ou mode `no-cache`
    observé), `::file fetched once` (aller `#/ticker/AAPL` → `#/` → `#/ticker/AAPL` : une seule requête
    `tickers/AAPL.json`).
  - Fichiers : `dashboard/e2e/loading.spec.ts`.
  - Fini quand : e2e vert ; qualité dashboard verte.

## Intégration continue, performance, documentation

- [ ] **T23** Tests du dashboard en CI — R25
  - Tests : `tests/test_repo_hygiene.py::test_ci_dashboard_job_runs_dashboard_tests` (le job `dashboard` exécute
    `npm test`, installe Chromium avec `--with-deps` et exécute `npm run test:e2e`, dans cet ordre, après le contrôle des
    types générés) ; tests existants : timeout ≤ 15, actions épinglées par SHA.
  - Fichiers : `.github/workflows/ci.yml` (étapes `npm test`, cache `~/.cache/ms-playwright` par version de
    `@playwright/test`, `npx playwright install --with-deps chromium`, `npm run test:e2e`, `timeout-minutes: 15`),
    `tests/test_repo_hygiene.py`.
  - Fini quand : qualité verte ; la CI de la PR passe les deux jobs ; durée du job `dashboard` relevée dans cette tâche.

- [ ] **T24** Mesure Lighthouse — R26
  - Tests : aucun test automatisé (hors CI, décision Q6 de la spec). Commande : `npm run lighthouse`.
  - Fichiers : `dashboard/package.json` (devDependency `lighthouse`, script `lighthouse`), `package-lock.json`,
    `dashboard/scripts/lighthouse.mjs` (build `dist-lh/` avec la fixture `m1` copiée dans `data/`, `vite preview`,
    3 mesures mobile avec le Chromium de Playwright, médiane, octets transférés, code 1 sous les seuils).
  - Fini quand : `npm run lighthouse` sort en 0 avec score médian ≥ 90 et < 5 Mo transférés ; résultats (3 scores,
    LCP, octets) consignés dans cette tâche. Si le score est insuffisant : s'arrêter et mesurer avant d'optimiser.

- [ ] **T25** Documentation — R23, R24, R25, R26
  - Tests : `tests/test_repo_hygiene.py::test_readme_documents_dashboard` (section Dashboard : pages livrées,
    `npm run dev`, `npm test`, `npm run test:e2e`, `npm run lighthouse`, régénération des fixtures),
    `::test_docs_list_dashboard_layout` (`CLAUDE.md` liste `dashboard/src/lib/` parmi les modules purs et les commandes
    ci-dessus ; `02-architecture.md` décrit `lib/`, `data/`, `pages/`, `components/`, `charts/`, `e2e/`,
    `tests/fixtures/`).
  - Fichiers : `README.md`, `CLAUDE.md`, `specs/02-architecture.md`.
  - Fini quand : tests verts ; qualité verte.

- [ ] **T26** Smoke test réel (manuel) — R1, R2, R6, R12, R15, R17
  - Tests : aucun test automatisé. Procédure : `uv run th export` sur les données réelles du dépôt, `npm run build`
    puis `npm run preview` ; parcourir `#/`, trois fiches ticker (dont SPY), `#/inconnu`, dans les deux thèmes et à
    375 px ; puis un build avec `TH_DASHBOARD_BASE=/TradingHelper/`.
  - Fichiers : aucun fichier de production ; résultat consigné dans cette tâche (`data_as_of`, état de fraîcheur, tailles
    transférées sur l'Overview et une fiche, erreurs console).
  - Fini quand : 21 lignes sur l'Overview, fiches lisibles avec indicateurs, aucune erreur console, aucune requête
    `tickers/*` sur l'Overview.

- [ ] **T_final** Vérification : tous les critères d'acceptation M1 de la spec (→ `/spec-verify F09`)

## Couverture exigences → tâches
| Exigence | Tâches |
|---|---|
| R1 Statique, hash, liens profonds, page introuvable | T5, T11, T26 |
| R2 Manifest `no-cache`, `?v=`, chargement à la demande, chunk du graphique | T1, T8, T15, T17, T22, T26 |
| R3 Erreurs nommant le fichier | T8, T12 |
| R4 États vides, sélecteurs masqués, aucune donnée | T12, T15, T16 |
| R5 Bandeau P8 sur toutes les routes | T10, T11 |
| R6 `data_as_of` et données périmées | T3, T13, T26 |
| R7 Thème à trois états, persistant, graphiques compris | T7, T14, T19 |
| R8 Contrastes AA, haussier/baissier non chromatique, clavier | T2, T14, T15, T17, T18, T20 |
| R9 Utilisable à 375 px | T20 |
| R10 URL relatives à `BASE_URL` | T1, T11, T21 |
| R11 Formats `fr-FR`, dates civiles | T2, T3 |
| R12 Overview : symboles, sparklines, benchmark | T15, T26 |
| R13 `[M3]` KPIs, leaderboard, signaux | T15 (état vide M1 seulement) |
| R14 Résolution du symbole | T5, T16 |
| R15 Graphique, overlays, RSI, warm-up | T4, T17, T26 |
| R16 Sélecteur de période | T4, T16, T17 |
| R17 Marqueurs, sélecteur de stratégie, détail P8 | T6, T18, T26 |
| R18 `[M3]` Fiche signal du jour | T16 (état vide M1 seulement) |
| R19 `[M3]` Portfolios | — (M3, décision 4 du plan) |
| R20 `[M3]` Portfolio | — (M3, décision 4 du plan) |
| R21 `[M3]` Models | — (M3, décision 4 du plan) |
| R22 `[M3]` Health | — (M3, décision 4 du plan) |
| R23 Tests Vitest de `lib/` | T1–T7, T25 |
| R24 Fixtures générées et validées | T9, T25 |
| R25 E2e Playwright en CI | T10, T23, T25 |
| R26 Lighthouse ≥ 90, < 5 Mo | T24, T25 |

20/20 exigences M1 couvertes (R13 et R18 pour leur état vide M1) ; R19–R22 hors de ce découpage (M3).

## Couverture critères d'acceptation M1 → tâches
| Critère (spec, M1) | Tâches |
|---|---|
| Lien profond, « Page introuvable », `#/portfolios` non livrée | T11 |
| Overview sans `tickers/*`, `?v=`, manifest `no-cache`, chunk du graphique | T15, T17, T22 |
| 404, JSON invalide, `schema_version: 2` → message, bandeau, pas d'exception | T12 |
| Fixture `empty` ; sections M3 vides ; sélecteur de stratégie masqué | T12, T15, T16 |
| Texte exact de P8 sur chaque route, erreurs comprises | T10, T11 |
| `data_as_of` affiché ; +3 → pas d'alerte, +4 → périmé ; week-end et férié | T3, T13 |
| Bascule sans rechargement, persistante, « système » suit le schéma émulé | T7, T14, T19 |
| axe sans violation de contraste ; bougies creuses ; ▲ BUY / ▼ SELL ; clavier | T14, T17, T18, T20 |
| `scrollWidth <= 375` sur chaque route | T20 |
| Build `/TradingHelper/` servi sous ce chemin | T21 |
| Formats `232,40 $`, `0,1234 $`, `+0,63 %`, `23/11/2026`, `—` ; fuseaux | T2, T3 |
| Une ligne par symbole, sparkline, benchmark, lien vers la fiche | T15 |
| `brk.b` → `BRK.B`, `BRK%2DB` → `BRK-B`, `ZZZ` → message | T5, T16 |
| SMA200 « historique insuffisant », warm-up non tracé, SMA20/50 par défaut | T4, T17 |
| 1M → première barre ≥ 2026-10-23 ; 5A sur 2 ans → série complète ; défaut 6M | T4, T16, T17 |
| Marqueurs BUY 20/11 et SELL 23/11, pas de HOLD, date hors série ignorée | T6, T18 |
| `npm test` vert ; `pytest` valide les fixtures | T1–T9 |
| `npm run test:e2e` sur `empty`, `m1`, `m1-signals` ; CI exécute les deux suites | T10, T23 |
| `npm run lighthouse` ≥ 90, < 5 Mo | T24 |

19/19 critères M1 couverts.
