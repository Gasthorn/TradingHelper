# Plan — F09 Dashboard GitHub Pages

> Généré par `/spec-plan`. À relire et valider avant `/spec-tasks`.
> **Portée** : ce plan détaille les exigences `[M1]` (R1–R12, R14–R17, R23–R26). Les exigences `[M3]` (R13, R18–R22)
> ne sont qu'esquissées : leur conception dépend des pré-requis de contrat listés dans la spec (formats
> `portfolios/*` et `models.json`, extension de `health.runs`). Le plan sera complété avant le découpage des tâches M3.

## Résumé de l'approche
F09 remplace la page « Hello » de F00 par une application Preact monopage qui lit **uniquement** les fichiers de
`th export` (F08). Pas de bibliothèque de routage ni d'état : un routeur par hash d'une trentaine de lignes, des hooks
Preact et un chargeur de données avec cache mémoire suffisent pour six routes.

Le code suit le même découpage pur / effets de bord que le pipeline Python :

1. **`src/lib/`** (**pur**, sans DOM ni `fetch`) : formats `fr-FR`, dates civiles et fraîcheur, analyse des routes,
   URL des données, filtrage par période, sélection des marqueurs, résolution du thème, base 100. C'est la cible des
   tests Vitest (R23).
2. **`src/data/loader.ts`** (effets de bord) : `fetch` du manifest (`no-cache`), puis de chaque fichier à
   `<BASE_URL>data/<path>?v=<sha256>`, une seule fois par visite ; erreurs typées (`missing`, `invalid_json`,
   `schema_version`) pour R3.
3. **`src/pages/`**, **`src/components/`** : rendu Preact. Chaque page gère ses trois états (chargement, erreur, vide).
4. **`src/charts/`** : seul endroit qui importe `lightweight-charts` (M1), puis `uplot` (M3). La page Ticker les charge
   par `import()` dynamique : ils sortent du bundle initial (R2, R26).

**Bandeau P8 en HTML statique.** Il reste dans `index.html`, hors de l'application : il est donc présent sur toutes les
routes, pages d'erreur comprises, et même si le JavaScript échoue (R5).

**Thème sans flash.** Un court script inline dans `<head>` lit `localStorage` et pose `data-theme` sur `<html>` avant le
premier rendu. Les couleurs sont des variables CSS ; les graphiques lisent ces variables et se reconfigurent à chaque
changement de thème (R7).

**Fixtures générées, commitées, contrôlées.** Un module Python de test produit les jeux `empty`, `m1` et `m1-signals`
avec `export()` de F08 (horloge et `git_sha` figés, prix synthétiques seedés). Un test `pytest` vérifie qu'ils sont à
jour et conformes à `schemas/` (R24). Côté e2e, Playwright **intercepte** les requêtes `**/data/**` et sert la fixture
voulue : une seule build sert tous les scénarios, y compris les erreurs 404 / JSON invalide de R3.

## Vérification constitution
| Principe | Impact | Comment il est respecté |
|---|---|---|
| P1 | Faible | Aucun calcul d'indicateur ni de signal côté client : séries et marqueurs affichés tels qu'exportés (R16, Hors périmètre). Le filtrage par période ne fait que masquer des barres. |
| P2 | Aucun | Pas de logique de décision dans le front. |
| P3 | M3 | Baselines toujours affichées et distinguées dans le leaderboard, Portfolios et Models (R13, R19, R21), tests e2e dédiés sur la fixture `m3`. En M1, sections présentes en état vide. |
| P4 | Moyen | `package-lock.json` verrouille les nouvelles dépendances. Fixtures produites de façon déterministe (générateur seedé, horloge et `git_sha` figés) et contrôlées par un test de synchronisation. E2e avec horloge figée (`page.clock`). |
| P5 | Moyen | Le front ne consomme que des fichiers conformes aux `schemas/` (types générés, F08 R5) ; les fixtures sont validées par `jsonschema` (R24). `dashboard/public/data/` reste non commité ; les fixtures vivent dans `dashboard/tests/fixtures/`. |
| P6 | Moyen | Job CI `dashboard` : installation de Chromium seul (`playwright install --with-deps chromium`), e2e sur build statique, estimation < 4 min de plus ; `timeout-minutes` porté de 10 à 15 (plafond de `test_repo_hygiene`). Lighthouse hors CI. Aucun secret. |
| P7 | Moyen | Un fichier absent, du JSON invalide ou un `schema_version` inattendu donnent un message nommant le fichier, sans écran blanc (R3). Une stratégie ou une date de marqueur inconnue n'interrompt jamais le rendu (R17). |
| P8 | **Fort** | Bandeau statique dans `index.html` (R5), vérifié sur chaque route en e2e et par `check:dist`. Chaque marqueur et chaque signal affiche confiance, `model_id` et `sharpe_oos` (R13, R17, R18) via `lib/markers.ts`, testé unitairement. |
| P9 | **Fort** | TypeScript strict (config existante : `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`), ESLint `strictTypeChecked`, types générés depuis `schemas/`. Tests unitaires (Vitest) et e2e (Playwright) en CI. |

## Fichiers
| Fichier | Action | Rôle |
|---|---|---|
| `dashboard/index.html` | modifier | Titre « TradingHelper » (question 1), bandeau P8 statique conservé, script inline de thème dans `<head>`, `<div id="app">` (l'en-tête passe dans l'app). |
| `dashboard/src/main.tsx` | modifier | Monte `<App />`. |
| `dashboard/src/App.tsx` | modifier | Coque : en-tête, navigation, aiguillage des routes, chargement du manifest. |
| `dashboard/src/style.css` | modifier | Variables de thème (clair / sombre via `data-theme`), mise en page mobile d'abord, tableaux défilants, focus visible, cibles 44 px. |
| `dashboard/src/lib/format.ts` | créer | Formats `fr-FR` : prix, montants, pourcentages, confiance, dates, `null` → « — » (R11). |
| `dashboard/src/lib/dates.ts` | créer | Dates civiles (`CivilDate` = chaîne `YYYY-MM-DD`), date du jour à New York, `S'`, retard, état périmé, borne de période (R6, R16, Définitions). |
| `dashboard/src/lib/routes.ts` | créer | `parseHash` → union `Route` ; décodage et normalisation du symbole (R1, R14). |
| `dashboard/src/lib/urls.ts` | créer | `dataUrl(base, entry)` avec `?v=` (R2, R10). |
| `dashboard/src/lib/series.ts` | créer | Découpage des séries par période, conversion `null` → point absent, détection d'une série entièrement nulle (R15, R16). |
| `dashboard/src/lib/markers.ts` | créer | Options du sélecteur de stratégie, filtrage, alignement sur les dates de la série, enrichissement P8 depuis `manifest.strategies` (R17). |
| `dashboard/src/lib/theme.ts` | créer | Préférence `light | dark | system`, lecture/écriture `localStorage` tolérante, résolution avec `prefers-color-scheme` (R7). |
| `dashboard/src/lib/base100.ts` | créer (M3) | Base 100 d'une courbe (R19). |
| `dashboard/src/lib/*.test.ts` | créer | Tests Vitest de chaque module de `lib/` (R23). |
| `dashboard/src/data/loader.ts` | créer | `loadManifest`, `loadFile<T>` : `fetch`, cache mémoire, `DataError` typée (R2, R3). |
| `dashboard/src/data/useData.ts` | créer | Hook Preact `useFile(path)` → `{ status: "loading" | "ok" | "error", … }`. |
| `dashboard/src/hooks/useRoute.ts`, `useTheme.ts` | créer | Écoute de `hashchange`, préférence de thème et `matchMedia`. |
| `dashboard/src/components/Header.tsx` | créer | Titre, navigation, `data_as_of`, badge « Données périmées (N séances) », bascule de thème (R6, R7). |
| `dashboard/src/components/ErrorPanel.tsx`, `EmptyState.tsx` | créer | Message d'erreur nommant le fichier (R3), état vide (R4). |
| `dashboard/src/components/Change.tsx` | créer | Variation signée avec ▲/▼ (R8, R12). |
| `dashboard/src/components/Sparkline.tsx` | créer | SVG inline, sans bibliothèque, avec `aria-label` (dernière valeur) (R12, Q7). |
| `dashboard/src/components/ScrollTable.tsx` | créer | Conteneur de tableau à défilement horizontal propre (R9). |
| `dashboard/src/pages/Overview.tsx` | créer | Tableau des symboles (R12) ; sections M3 en état vide (R4, R13). |
| `dashboard/src/pages/Ticker.tsx` | créer | Résolution du symbole, sélecteurs (période, overlays, stratégie), import dynamique du graphique, détail du marqueur ; fiche signal vide en M1 (R14–R18). |
| `dashboard/src/pages/NotFound.tsx` | créer | « Page introuvable » + lien vers l'Overview (R1). |
| `dashboard/src/charts/priceChart.ts` | créer | Enveloppe `lightweight-charts` : chandeliers creux/pleins, volume, overlays, panneau RSI (lignes 30/70), marqueurs ▲/▼ libellés, thème (R8, R15, R17). |
| `dashboard/src/pages/{Portfolios,Portfolio,Models,Health}.tsx`, `src/charts/lineChart.ts` | créer (M3) | Pages M3 (R19–R22), `uplot`. |
| `dashboard/vite.config.ts` | modifier | Section `test` de Vitest (environnement `node`, `src/**/*.test.ts`). |
| `dashboard/tsconfig.json` | modifier | Inclure `e2e/` et `playwright.config.ts` ; types `vitest`. |
| `dashboard/eslint.config.js` | modifier | Ignorer `test-results/`, `playwright-report/`, `dist-*/`. |
| `dashboard/package.json`, `package-lock.json` | modifier | Dépendances (voir ci-dessous) ; scripts `test`, `test:e2e`, `lighthouse`. |
| `dashboard/playwright.config.ts` | créer | Chromium ; deux serveurs `vite preview` : base `/` (port 4173) et base `/TradingHelper/` (port 4174, build dans `dist-base/`) ; projet « mobile » 375 × 812. |
| `dashboard/e2e/support.ts` | créer | `useFixture(page, name)` (interception `**/data/**`), `failFile(page, path, kind)`, horloge figée, collecte des erreurs console. |
| `dashboard/e2e/*.spec.ts` | créer | `routing`, `loading`, `errors`, `empty`, `disclaimer`, `freshness`, `theme`, `a11y`, `mobile`, `base`, `overview`, `ticker` (R1–R10, R12, R14–R17, R25). |
| `dashboard/scripts/lighthouse.mjs` | créer | Build avec la fixture `m1` copiée dans `dist-lh/data/`, `vite preview`, 3 mesures Lighthouse mobile avec le Chromium de Playwright, médiane, octets transférés ; code 1 sous les seuils (R26). |
| `dashboard/scripts/check-dist.mjs` | modifier | Titre attendu « TradingHelper » (question 1). |
| `dashboard/tests/fixtures/{empty,m1,m1-signals}/` | générer | Jeux d'export commités (R24). |
| `tests/dashboard_fixtures.py` | créer | Construction des fixtures : config d'univers dédiée, prix synthétiques seedés, rapports et signaux de `tests/fixtures/export/`, appel de `export()` (F08) avec horloge et `git_sha` figés. `python -m tests.dashboard_fixtures` réécrit le dossier. |
| `tests/test_dashboard_fixtures.py` | créer | Fixtures à jour (régénération en dossier temporaire == commité) et conformes à `schemas/*.schema.json` (R24). |
| `.github/workflows/ci.yml` | modifier | Job `dashboard` : `npm test`, installation de Chromium, `npm run test:e2e` ; `timeout-minutes: 15` (R25). |
| `tests/test_repo_hygiene.py` | modifier | Le job `dashboard` exécute `npm test` et `npm run test:e2e` (R25). |
| `.gitignore` | modifier | `dashboard/test-results/`, `dashboard/playwright-report/`, `dashboard/dist-*/`. |
| `specs/02-architecture.md` | modifier | Arborescence du dashboard : `lib/` (pur), `data/`, `pages/`, `components/`, `charts/`, `e2e/`, `tests/fixtures/`. |
| `specs/features/F00-bootstrap/spec.md` | modifier | R12 : titre « TradingHelper » (question 1). |
| `CLAUDE.md` | modifier | Commandes `npm test`, `npm run test:e2e`, `npm run lighthouse`, régénération des fixtures ; `dashboard/src/lib/` parmi les modules purs. |
| `README.md` | modifier | Section Dashboard : pages, développement local, tests. |

## Interfaces / signatures
```ts
// src/lib/dates.ts   (pur : la date du jour est toujours un paramètre)
export type CivilDate = string;                         // "YYYY-MM-DD", jamais convertie en instant
export function dayNumber(d: CivilDate): number;        // jours depuis 1970-01-01 via Date.UTC (aucun fuseau)
export function fromDayNumber(n: number): CivilDate;
export function todayInNewYork(now: Date): CivilDate;   // Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" })
export function lastAssumedSession(today: CivilDate): CivilDate;            // S' : dernier lun–ven < today
export function sessionsBehind(d: CivilDate, today: CivilDate): number;     // lun–ven dans ]d, S']
export const STALE_AFTER = 3;
export function freshness(dataAsOf: CivilDate | null, today: CivilDate):
  | { kind: "none" } | { kind: "fresh"; behind: number } | { kind: "stale"; behind: number };
export type Period = "1M" | "6M" | "1A" | "5A" | "Max";
export function periodStart(last: CivilDate, period: Period): CivilDate | null;  // null pour Max ; fin de mois bornée

// src/lib/format.ts   (Intl.NumberFormat("fr-FR"))
export function formatPrice(x: number | null): string;      // 2 décimales si ≥ 1, sinon 4 ; « 232,40 $ »
export function formatAmount(x: number | null): string;     // « 1 234,56 $ »
export function formatPercent(x: number | null, opts?: { signed?: boolean }): string; // « +0,63 % »
export function formatConfidence(x: number | null): string; // « 67 % »
export function formatDate(d: CivilDate | null): string;    // « 23/11/2026 »
export const EMPTY = "—";

// src/lib/routes.ts
export type Route =
  | { page: "overview" }
  | { page: "ticker"; symbol: string }      // décodé, en majuscules
  | { page: "not_found" };                  // M3 : portfolios, portfolio, models, health
export function parseHash(hash: string): Route;

// src/lib/urls.ts
export function dataUrl(base: string, entry: { path: string; sha256: string }): string; // `${base}data/${path}?v=${sha256}`
export const MANIFEST_PATH = "manifest.json";

// src/lib/series.ts
export interface BarWindow { from: number; to: number }                       // indices inclusifs
export function periodWindow(dates: readonly CivilDate[], period: Period): BarWindow;
export function linePoints(dates: readonly CivilDate[], values: readonly (number | null)[], w: BarWindow):
  { time: CivilDate; value: number }[];                                    // null exclus (R15)
export function isAllNull(values: readonly (number | null)[]): boolean;

// src/lib/markers.ts
export function strategyOptions(markers: readonly ExportMarker[]): string[];   // triés, uniques
export interface MarkerView extends ExportMarker { modelId: string | null; sharpeOos: number | null; known: boolean }
export function visibleMarkers(markers: readonly ExportMarker[], strategy: string | null,
  dates: ReadonlySet<CivilDate>, strategies: readonly ManifestStrategy[]): MarkerView[];

// src/lib/theme.ts
export type ThemePreference = "light" | "dark" | "system";
export const THEME_KEY = "th-theme";
export function parsePreference(raw: string | null): ThemePreference;     // valeur inconnue → "system"
export function resolveTheme(pref: ThemePreference, prefersDark: boolean): "light" | "dark";

// src/data/loader.ts   (effets de bord)
export type DataErrorKind = "missing" | "invalid_json" | "schema_version";
export class DataError extends Error { readonly path: string; readonly kind: DataErrorKind }
export const EXPECTED_SCHEMA_VERSION = 1 as const;   // ManifestFile["schema_version"]
export function loadManifest(fetchFn?: typeof fetch): Promise<ManifestFile>;  // cache: "no-cache"
export function loadFile<T extends { schema_version: number }>(manifest: ManifestFile, path: string): Promise<T>;
// un fichier absent de manifest.files → DataError("missing") ; résultat mémorisé par path

// src/charts/priceChart.ts   (importé dynamiquement par pages/Ticker.tsx)
export interface PriceChartOptions { overlays: { sma20: boolean; sma50: boolean; sma200: boolean; bollinger: boolean } }
export interface PriceChart {
  setData(series: TickerSeries, window: BarWindow): void;
  setOverlays(o: PriceChartOptions["overlays"]): void;
  setMarkers(markers: readonly MarkerView[]): void;
  setTheme(theme: "light" | "dark"): void;
  destroy(): void;
}
export function createPriceChart(container: HTMLElement, opts: PriceChartOptions): PriceChart;
```
```python
# tests/dashboard_fixtures.py
FIXTURE_NAMES = ("empty", "m1", "m1-signals")
FIXTURES_DIR = REPO_ROOT / "dashboard" / "tests" / "fixtures"
FROZEN_NOW = datetime(2026, 11, 23, 22, 50, tzinfo=UTC); FROZEN_SHA = "0" * 40

def build_fixture(name: str, out: Path) -> None: ...   # données dans un dossier temporaire puis export()
def main(argv: Sequence[str] | None = None) -> int: ... # python -m tests.dashboard_fixtures [--check]
```
Contenu prévu des fixtures (seed 9, séances NYSE se terminant le 2026-11-23) : AAPL (300 séances, dates des signaux
F08 incluses), BRK.B (150 séances : `sma200` entièrement nulle, symbole avec point), NVDA (cours sous 1 $ : prix à
4 décimales), SPY (benchmark). `empty` : univers sans aucun fichier de prix. `m1-signals` : `m1` + les signaux de
`tests/fixtures/export/signals/`.

**Graphique (lightweight-charts v5).** Panneau 0 : chandeliers (`upColor` transparent + `borderUpColor` → creux ;
baissiers pleins), overlays en `LineSeries`, volume en `HistogramSeries` sur une échelle de prix secondaire ;
panneau 1 : RSI avec `createPriceLine` à 30 et 70. Marqueurs par `createSeriesMarkers` : BUY `arrowUp` `belowBar`
texte « BUY », SELL `arrowDown` `aboveBar` texte « SELL ». Le temps est passé en chaînes `YYYY-MM-DD` (jours ouvrés,
pas de fuseau). Le détail d'un marqueur est affiché dans une légende sous le graphique (accessible au clavier), mise à
jour par `subscribeCrosshairMove` et par une liste des marqueurs visibles.

## Traçabilité exigences → design → tests
| Exigence | Élément de design | Test(s) prévu(s) |
|---|---|---|
| R1 | `lib/routes.ts`, `pages/NotFound.tsx`, aiguillage dans `App.tsx` | `routes.test.ts::parseHash` (routes connues, inconnues, M3 non livrées) ; `e2e/routing.spec.ts::deep link reload`, `::unknown route`, `::portfolios not delivered` |
| R2 | `data/loader.ts` (`no-cache`, `?v=`, cache), import dynamique dans `pages/Ticker.tsx` | `urls.test.ts::dataUrl` ; `e2e/loading.spec.ts::overview loads only manifest and overview`, `::urls carry manifest hash`, `::manifest no-cache`, `::chart chunk only on ticker`, `::file fetched once` |
| R3 | `DataError`, `ErrorPanel.tsx` | `e2e/errors.spec.ts::overview 404`, `::invalid json`, `::schema_version 2`, `::manifest missing` (bandeau présent, aucune `pageerror`) |
| R4 | `EmptyState.tsx`, sélecteurs conditionnels | `e2e/empty.spec.ts::empty fixture no data`, `::m1 sections empty`, `::strategy selector hidden` |
| R5 | Bandeau statique de `index.html` | `e2e/disclaimer.spec.ts::exact P8 text on every route` (routes, erreur, introuvable) ; `npm run check:dist` |
| R6 | `lib/dates.ts::freshness`, `Header.tsx` | `dates.test.ts::sessionsBehind` (semaine, week-end, férié compté, avant `S'`), `::freshness` (null, +3, +4) ; `e2e/freshness.spec.ts::+3 fresh`, `::+4 stale` (`page.clock`) |
| R7 | `lib/theme.ts`, `hooks/useTheme.ts`, script inline, `PriceChart.setTheme` | `theme.test.ts::parsePreference`, `::resolveTheme` ; `e2e/theme.spec.ts::toggle without reload`, `::persists after reload`, `::system follows emulated scheme`, `::chart background follows theme` |
| R8 | Palette CSS, chandeliers creux, `Change.tsx`, marqueurs libellés, focus visible | `e2e/a11y.spec.ts::no contrast violation light|dark` (`@axe-core/playwright`, règle `color-contrast`), `::keyboard reaches period selector` ; `e2e/ticker.spec.ts::hollow up candles`, `::marker labels` ; `format.test.ts::signed change arrow` |
| R9 | CSS mobile d'abord, `ScrollTable.tsx` | `e2e/mobile.spec.ts::no horizontal scroll` (chaque route livrée, 375 × 812), `::touch targets 44px` |
| R10 | `import.meta.env.BASE_URL` partout (`urls.ts`, liens) | `urls.test.ts::base prefix` ; `e2e/base.spec.ts::served under /TradingHelper/` (aucune requête hors préfixe) |
| R11 | `lib/format.ts`, `lib/dates.ts` | `format.test.ts` (`232,40 $`, `0,1234 $`, `1 234,56 $`, `+0,63 %`, `67 %`, `23/11/2026`, `null` → `—`) ; `dates.test.ts::civil date stable` (exécuté sous `TZ=America/Los_Angeles` et `TZ=Pacific/Auckland`) |
| R12 | `pages/Overview.tsx`, `Sparkline.tsx` | `e2e/overview.spec.ts::one row per symbol with sparkline`, `::benchmark flagged`, `::row links to ticker` |
| R13 | (M3) sections Overview | Esquisse : `e2e/overview.spec.ts` sur fixture `m3` (baselines, filtres, P8) ; en M1 : `e2e/empty.spec.ts::m1 sections empty` |
| R14 | `routes.ts` (décodage, majuscules), résolution dans `pages/Ticker.tsx` | `routes.test.ts::decodes and uppercases` ; `e2e/ticker.spec.ts::brk.b case-insensitive`, `::unknown symbol message` |
| R15 | `charts/priceChart.ts`, `lib/series.ts` | `series.test.ts::linePoints skips null`, `::isAllNull` ; `e2e/ticker.spec.ts::sma200 disabled short history`, `::default overlays` |
| R16 | `lib/dates.ts::periodStart`, `lib/series.ts::periodWindow` | `dates.test.ts::periodStart` (31 → 30 jours, 29 février), `series.test.ts::periodWindow` (historique court, Max) ; `e2e/ticker.spec.ts::1M first bar`, `::default 6M` |
| R17 | `lib/markers.ts`, `PriceChart.setMarkers`, légende | `markers.test.ts::strategyOptions`, `::filters by strategy`, `::drops dates outside series`, `::P8 enrichment unknown strategy` ; `e2e/ticker.spec.ts::m1-signals markers on 20/11 and 23/11` |
| R18 | (M3) fiche signal, `overview.latest_signals` | Esquisse : `e2e/ticker.spec.ts` sur `m3` ; en M1 : état vide (`e2e/empty.spec.ts`) |
| R19–R22 | (M3) pages, `lib/base100.ts`, `charts/lineChart.ts` | Esquisse : `base100.test.ts`, `e2e/{portfolios,portfolio,models,health}.spec.ts` sur `m3` |
| R23 | `src/lib/*.test.ts`, Vitest | `npm test` en CI |
| R24 | `tests/dashboard_fixtures.py` | `tests/test_dashboard_fixtures.py::test_fixtures_up_to_date[empty|m1|m1-signals]`, `::test_fixtures_match_json_schemas` |
| R25 | `playwright.config.ts`, `e2e/`, `ci.yml` | `npm run test:e2e` en CI ; `test_repo_hygiene.py::test_ci_dashboard_job_runs_dashboard_tests` |
| R26 | `scripts/lighthouse.mjs`, découpage du bundle | `npm run lighthouse` à la vérification (médiane ≥ 90, < 5 Mo) |

## Dépendances ajoutées
Versions : majeure courante à l'implémentation, fixée par `package-lock.json` (P4).

| Paquet | Type | Justification |
|---|---|---|
| `lightweight-charts` (v5) | dépendance | Prévu par `02-architecture.md` : chandeliers, histogramme, panneaux multiples (RSI), marqueurs natifs ; ≈ 45 Ko gzip, chargé seulement sur Ticker. Apache-2.0 : l'attribution TradingView (logo par défaut) est conservée. |
| `uplot` | dépendance (M3) | Prévu par `02-architecture.md` : courbes d'equity, drawdown, calibration ; ≈ 20 Ko. Ajouté avec les tâches M3, pas avant. |
| `vitest` | dev | Tests unitaires de `lib/` (R23) ; réutilise la config Vite, TypeScript sans étape de compilation. |
| `@playwright/test` | dev | E2e (R25) : interception réseau (fixtures, erreurs R3), horloge figée (`page.clock`, R6), émulation 375 px et `prefers-color-scheme` (R7, R9). |
| `@axe-core/playwright` | dev | Contrôle automatique des contrastes WCAG AA dans les deux thèmes (R8). |
| `lighthouse` | dev | Mesure R26 par `npm run lighthouse`, en local, avec le Chromium déjà installé par Playwright (pas en CI). |

Aucune dépendance Python ajoutée (`jsonschema` et `numpy` sont déjà présents). Pas de bibliothèque de routage, d'état ni
de composants : le besoin (six routes, données en lecture seule) ne le justifie pas.

## Risques & mitigations
- **Validation des données à l'exécution limitée.** Les types TS n'existent qu'à la compilation ; le loader vérifie
  seulement JSON, objet et `schema_version` (R3). Un fichier mal formé mais de bonne version pourrait casser un rendu.
  Mitigation : les fichiers sont validés par schéma à la production (F08) et les fixtures par `pytest` ; chaque page
  est entourée d'une limite d'erreur Preact qui affiche `ErrorPanel` au lieu d'un écran blanc. Pas d'`ajv` (≈ 120 Ko).
- **Approximation du calendrier** : un férié compte comme une séance (Q2), donc l'alerte peut apparaître une séance
  plus tôt (ex. après Thanksgiving). Assumé par la spec ; testé explicitement.
- **Lighthouse ≥ 90 sur mobile simulé** : Preact + données ≈ 10 Ko gzip pour l'Overview ; `lightweight-charts` hors du
  bundle initial ; pas de police web. Si le score est insuffisant, s'arrêter et mesurer avant d'optimiser au hasard.
- **Coût CI de Playwright** : installation de Chromium ≈ 1–2 min (mise en cache de `~/.cache/ms-playwright` par clé de
  version). Plafond de 15 min déjà imposé par `test_repo_hygiene`.
- **Fragilité des tests de graphique** : le canvas n'est pas inspectable. Mitigation : la logique (points, marqueurs,
  fenêtre) est dans `lib/` et testée unitairement ; l'e2e vérifie la légende et les options appliquées via un attribut
  `data-*` de test exposé par `PriceChart` (ex. nombre de marqueurs, overlays actifs), pas les pixels.
- **Fixtures périmées après une évolution de F08** : le test `test_fixtures_up_to_date` échoue alors en CI, avec la
  commande de régénération dans le message.
- **Contraste des couleurs haussier/baissier** sur fond sombre : palette choisie et vérifiée par axe-core dès la première
  tâche de thème, pas en fin de feature.
- **Fuseau du poste de développement** : les tests `dates.test.ts` sont lancés sous deux fuseaux extrêmes (variable `TZ`
  dans le script `test`), ce qui détecte toute conversion implicite en instant.

## ADR
Aucun ADR requis : Preact, `lightweight-charts` et `uplot` sont déjà fixés par `02-architecture.md` (F00 Q1) ; la
fraîcheur côté client, les fixtures commitées et la répartition des tests ont été décidées dans la spec (Q2, Q5, Q6).
Le routeur maison et l'absence de bibliothèque d'état sont des choix locaux, réversibles, documentés ici.

## Décisions (validées le 2026-11-25)
1. **Titre de la page** : « TradingHelper » ; F00 R12 et `scripts/check-dist.mjs` sont modifiés dans la même tâche que
   `index.html`.
2. **Critère R14** : `%5EGSPC` (impossible, `^` refusé par `SYMBOL_PATTERN`) remplacé dans la spec par `brk.b` → `BRK.B`
   et par le décodage `BRK%2DB` → `BRK-B` (test unitaire).
3. **Tests du graphique** : `PriceChart` expose son état (nombre de marqueurs, overlays actifs, thème) dans des
   attributs `data-*` du conteneur, lus par Playwright ; pas de captures d'écran de référence.
4. **Portée** : `/spec-tasks` ne découpe que les exigences `[M1]` ; le plan sera complété pour M3 une fois les formats
   `portfolios/*` et `models.json` fixés dans F08.

## Questions pour l'humain
Aucune pour M1.
