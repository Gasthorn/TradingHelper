# F09 — Dashboard GitHub Pages

- **Statut** : 🧭 Planned (2026-11-25)
- **Milestone** : M1 (exigences et critères `[M1]` : socle, Overview, Ticker) puis M3/M4 (`[M3]` : Portfolios,
  Portfolio, Models, Health, contenus dépendant des signaux et portefeuilles)
- **Dépend de** : F08 (M1 pour `[M1]`, M3 pour `[M3]`) ; F00 R14 (`base` Vite configurable)
- **Contrats** : `03-data-contracts.md` §7 (lecture) ; §4 et §5 via les fichiers d'export (lecture, M3)
- **Principes clés** : P3 (baselines toujours visibles), P8 (avertissement ; confiance + modèle + performance de chaque
  recommandation), P9 (TypeScript strict, tests)

## Objectif
Un site statique, rapide, lisible sur mobile, qui rend visibles marché, signaux, portefeuilles et performance des modèles,
à partir des seuls fichiers produits par `th export` (F08).

## User stories
- En tant que visiteur, j'ouvre le dashboard sur mon téléphone et je vois en moins de 2 s la date des données, les
  derniers cours et leurs variations, avec l'avertissement P8.
- En tant que visiteur, j'ouvre la fiche d'un ticker et je lis chandeliers, volume, SMA, Bollinger, RSI et les signaux
  BUY/SELL d'une stratégie, chacun avec sa confiance, son modèle et sa performance.
- En tant que visiteur, je compare les portefeuilles fictifs des modèles à ceux des baselines (M3).
- En tant qu'owner, je repère d'un coup d'œil des données périmées ou un run en échec.

## Pages
Vue d'ensemble ; le contenu exigible est dans les exigences citées.

| Route (hash) | Contenu | Milestone | Exigences |
|---|---|---|---|
| `#/` **Overview** | Date des données, tickers (cours, variation, sparkline) ; KPIs, leaderboard, derniers signaux filtrables | M1 / M3 | R12, R13 |
| `#/ticker/:symbol` | Chandeliers + volume, overlays SMA/Bollinger, panneau RSI, marqueurs, période ; fiche signal du jour | M1 / M3 | R14–R18 |
| `#/portfolios` | Equity superposées base 100 (baselines comprises), drawdown, métriques live | M3 | R19 |
| `#/portfolio/:id` | Equity, positions, journal des trades, événements `model_switch` | M3 | R20 |
| `#/models` | Leaderboard OOS, distribution des random traders (boîtes à moustaches), model cards, calibration | M3 | R21 |
| `#/health` | Fraîcheur par ticker, derniers runs par étape, avertissements qualité | M3 | R22 |

## Définitions
- **Date du jour** : date civile à New York (`America/New_York`) de l'horloge du navigateur. L'horloge est injectable
  (tests unitaires et e2e).
- **Dernière séance supposée `S'`** : dernier jour du lundi au vendredi **strictement antérieur** à la date du jour.
- **Retard d'une date `d`** : nombre de jours du lundi au vendredi dans l'intervalle `]d, S']` (0 si `d >= S'`).
  Approximation front du calendrier NYSE (Q2) : un jour férié compte comme une séance, ce qui peut avancer l'alerte d'une
  séance autour d'un férié ; la séance du jour n'est jamais exigée.
- **Périmé** : retard `> 3` (même seuil que F02 : `last_date < S − 3 séances`).
- **Date de séance** : chaîne `YYYY-MM-DD` du contrat, traitée comme date civile, jamais convertie en instant
  (pas de `new Date("YYYY-MM-DD")`, interprété en UTC).
- **Fixtures** : jeux d'export (§7) commités dans `dashboard/tests/fixtures/<nom>/` (Q5) : `empty` (aucun symbole,
  `data_as_of: null`), `m1` (prix et rapports de run seuls, sections M3 vides), `m1-signals` (`m1` + signaux AAPL : HOLD le
  2026-11-19, BUY le 2026-11-20, SELL le 2026-11-23, comme la fixture F08 R9), puis `m3` (portefeuilles, signaux,
  registre).
- **Base 100** : courbe divisée par sa première valeur et multipliée par 100.

## Exigences

### Socle
- **R1** `[M1]` Le site DOIT être 100 % statique et routé par hash, sans backend ni `404.html` : recharger n'importe quelle
  route `#/…` (lien profond) DOIT afficher la page demandée. QUAND la route est inconnue (y compris une route `[M3]` non
  encore livrée), le site DOIT afficher une page « Page introuvable » avec un lien vers l'Overview.
- **R2** `[M1]` Chargement des données :
  - `manifest.json` DOIT être chargé en premier, avec `cache: "no-cache"` ;
  - tout autre fichier DOIT être chargé à la demande, à l'URL `<BASE_URL>data/<path>?v=<sha256>` où `sha256` vient de
    l'entrée `files` du manifest (cache-busting, F08 R11), et au plus une fois par visite (cache mémoire) ;
  - l'Overview NE DOIT charger que `manifest.json` et `overview.json` (aucun `tickers/*`) ;
  - `lightweight-charts` DOIT être chargé par import dynamique depuis la page Ticker uniquement (absent du bundle initial).
- **R3** `[M1]` SI `manifest.json` ou un fichier requis est absent (statut HTTP ≠ 200), n'est pas du JSON, ou porte un
  `schema_version` différent de celui des types générés, ALORS la page DOIT afficher un message d'erreur nommant le
  fichier, en conservant bandeau et navigation, sans exception non interceptée ni erreur console non gérée.
- **R4** `[M1]` Chaque section dont la donnée est une liste vide ou `null` DOIT afficher un état vide explicite
  (ex. « Aucun signal pour l'instant ») ; un sélecteur sans option DOIT être masqué. QUAND `data_as_of` vaut `null`
  (aucun symbole exporté, premier run), l'Overview DOIT afficher « Aucune donnée disponible ».
- **R5** `[M1]` Chaque route, y compris les pages d'erreur et « Page introuvable », DOIT afficher le bandeau contenant le
  texte exact de P8 : « Outil expérimental et éducatif. Ceci n'est pas un conseil en investissement. »
- **R6** `[M1]` L'en-tête de chaque page DOIT afficher `data_as_of` ; QUAND `data_as_of` est périmé (Définitions), il DOIT
  afficher un état « Données périmées » mentionnant le retard en séances. Le calcul se fait dans le navigateur à partir de
  la date du jour, et non depuis `health.json` (figé au dernier export).
- **R7** `[M1]` Thème : trois choix — clair, sombre, système (défaut, `prefers-color-scheme`) —, mémorisés dans
  `localStorage` et appliqués immédiatement à toute la page, graphiques compris, sans rechargement.
- **R8** `[M1]` Accessibilité :
  - contraste WCAG AA (4,5:1 pour le texte, 3:1 pour les éléments graphiques significatifs) dans les deux thèmes ;
  - haussier/baissier jamais signalé par la seule couleur : bougies haussières creuses et baissières pleines, variations
    avec signe et flèche (▲/▼), marqueurs BUY ▲ sous la bougie avec le libellé « BUY » et SELL ▼ au-dessus avec « SELL » ;
  - navigation, bascules et sélecteurs utilisables au clavier, avec un focus visible.
- **R9** `[M1]` À 375 × 812 px, chaque route DOIT s'afficher sans défilement horizontal de la page
  (`document.documentElement.scrollWidth <= 375`) : les tableaux défilent dans leur propre conteneur, les graphiques
  prennent la largeur disponible, les cibles tactiles mesurent au moins 44 × 44 px.
- **R10** `[M1]` Toutes les URL (données, assets, liens) DOIVENT être résolues relativement à `import.meta.env.BASE_URL`,
  de sorte qu'un build avec `TH_DASHBOARD_BASE=/TradingHelper/` (F00 R14) servi sous `/TradingHelper/` fonctionne.
- **R11** `[M1]` Formats d'affichage (locale `fr-FR`, Q8), centralisés dans `lib/format.ts` :
  - dates de séance en `JJ/MM/AAAA` ;
  - prix à 2 décimales s'ils valent au moins 1, à 4 sinon ; montants avec séparateur de milliers et devise
    (`1 234,56 $`) ;
  - rendements, poids et métriques en pourcentage à 2 décimales, avec signe pour les variations ; confiance en
    pourcentage entier ;
  - `null` affiché « — ».

### Overview
- **R12** `[M1]` L'Overview DOIT lister chaque symbole de `overview.tickers` dans l'ordre du manifest, avec nom,
  `last_close`, `change_1d` (signe et flèche, R8) et une sparkline SVG inline tracée depuis `spark`, sans bibliothèque de
  graphiques (Q7). Le benchmark (`benchmark: true`) DOIT être signalé « indice de référence ». Chaque ligne DOIT mener à
  `#/ticker/:symbol`.
- **R13** `[M3]` L'Overview DOIT afficher :
  - les KPIs : `best_strategy_30d` et l'equity de chaque stratégie (lignes du `leaderboard`) ;
  - le `leaderboard`, baselines comprises et distinguées des modèles (P3) ;
  - les derniers signaux (`latest_signals`), filtrables par stratégie, action et symbole ; chaque signal affiche action,
    confiance, `strategy_id`, `model_id` (« baseline » si `null`) et `sharpe_oos` (P8).

  En M1, ces sections existent et sont en état vide (R4).

### Ticker
- **R14** `[M1]` `#/ticker/:symbol` DOIT décoder le symbole (`decodeURIComponent`, ex. `BRK%2DB` → `BRK-B`) et le comparer
  aux symboles du manifest sans tenir compte de la casse. SI le symbole est absent du manifest, ALORS la page DOIT
  afficher « Pas de données pour <symbole> » (R3 ne s'applique pas).
- **R15** `[M1]` Le graphique DOIT afficher chandeliers et volume (histogramme), les overlays activables SMA20, SMA50,
  SMA200 et Bollinger (bornes haute et basse ; au premier affichage : SMA20 et SMA50 actives, SMA200 et Bollinger
  inactives, Q10), et un panneau RSI14 avec les lignes 30 et 70. Les valeurs `null` (warm-up) NE DOIVENT PAS être tracées
  (ni zéro ni interpolation) ; une série entièrement `null` (ex. `sma200` sur moins de 200 barres) est désactivée avec la
  mention « historique insuffisant ».
- **R16** `[M1]` Le sélecteur de période (1M, 6M, 1A, 5A, Max ; défaut 6M, Q10) DOIT afficher les barres dont la date est
  postérieure ou égale à « dernière date du ticker − N mois calendaires » (Max : toutes). Si l'historique est plus court,
  toute la série est affichée. Les indicateurs exportés sont affichés tels quels (aucun recalcul côté client).
- **R17** `[M1]` Les `markers` du fichier DOIVENT être placés sur la bougie de même date, filtrés par un sélecteur de
  stratégie (options : les `strategy_id` présents dans `markers`, triés ; masqué s'il n'y en a aucun). Un marqueur dont la
  date est absente de la série n'est pas tracé et ne provoque aucune erreur. Le détail d'un marqueur (info-bulle ou
  légende) DOIT afficher date, action, confiance, stratégie, ainsi que `model_id` et `sharpe_oos` lus dans
  `manifest.strategies` (« — » si la stratégie n'y figure pas) (P8).
- **R18** `[M3]` La fiche « signal du jour » DOIT lister les signaux du symbole dans `overview.latest_signals`
  (`overview.json` chargé en plus du fichier ticker, Q4) : action, confiance, horizon, poids cible, stratégie, `model_id`,
  `sharpe_oos` (P8) et, si `explanation` est présente, ses contributions (feature et contribution signée, en barres
  horizontales) ; sinon « Pas d'explication disponible ». En M1, la fiche est en état vide (R4).

### Portfolios, Models, Health
- **R19** `[M3]` `#/portfolios` DOIT superposer les courbes d'equity de toutes les stratégies du manifest, baselines
  comprises et distinguées par le style de trait (P3), chacune en base 100 à sa propre date de création ; afficher la
  courbe de drawdown et le tableau des métriques live du contrat `portfolios/*` (F08 R17), sans recalculer de métrique.
- **R20** `[M3]` `#/portfolio/:id` DOIT afficher la courbe d'equity avec les événements `model_switch` annotés à leur date,
  la répartition des positions actuelles (en % de l'equity, cash compris), et le journal des trades par date décroissante.
  SI `id` est absent du manifest, ALORS la page affiche « Page introuvable » (R1).
- **R21** `[M3]` `#/models` DOIT afficher le leaderboard OOS (Sharpe, CAGR, MaxDD, percentile random), baselines
  comprises ; pour chaque métrique, la distribution des random traders en boîte à moustaches (P5–P95, P25–P75, médiane ;
  Q3) avec la position de chaque stratégie ; les model cards (champs du contrat §5) ; la courbe de calibration par décile
  de chaque modèle avec la diagonale de référence.
- **R22** `[M3]` `#/health` DOIT afficher :
  - par ticker de `health.tickers` : `last_date`, retard et état périmé calculés dans le navigateur (Définitions, R6) ;
  - les `runs` : une ligne par séance, un statut par étape présente (code de sortie et compteurs ; « — » si la section
    est `null`) ;
  - les `quality_warnings`, avec la mention « N avertissements non affichés » si `quality_warnings_truncated > 0`.

### Tests et performance
- **R23** `[M1]` `dashboard/src/lib/` DOIT être couvert par des tests unitaires Vitest : formats (R11), dates civiles,
  retard et état périmé (Définitions, horloge injectée), construction des URL (R2, R10), filtrage par période (R16),
  base 100 (R19).
- **R24** `[M1]` Les fixtures (Définitions) DOIVENT être produites par `th export` sur des données de `tests/fixtures/`,
  via un script documenté, et un test `pytest` DOIT vérifier leur conformité à `schemas/*.schema.json` (`jsonschema`,
  déjà utilisé par F08).
- **R25** `[M1]` Un test e2e Playwright (Chromium) DOIT, sur `vite build` + `vite preview` servant une fixture et avec une
  horloge figée, charger chaque route livrée au milestone courant et vérifier l'absence d'erreur console et les
  critères R1–R6, R9, R17. F09 ajoute les scripts `npm test` (Vitest) et `npm run test:e2e` (Playwright) et les étapes
  correspondantes au job `dashboard` de `ci.yml` (Q6).
- **R26** `[M1]` L'Overview DOIT obtenir un score Lighthouse performance ≥ 90 (profil mobile par défaut, médiane de 3
  mesures, `vite preview` sur la fixture `m1`), et transférer moins de 5 Mo (01-vision). La mesure est lancée par
  `npm run lighthouse` à la vérification, pas en CI (Q6).

## Critères d'acceptation

### M1
- [ ] Recharger `#/ticker/AAPL` affiche la fiche ; `#/inconnu` et `#/portfolios` (non livrée en M1) affichent « Page
  introuvable » avec lien vers l'Overview. (R1)
- [ ] Fixture `m1` : l'Overview ne fait aucune requête `tickers/*` ; toute requête de données hors manifest porte
  `?v=<sha256>` égal à celui du manifest ; le manifest est demandé en `no-cache` ; `lightweight-charts` n'apparaît que
  dans un chunk chargé sur la page Ticker. (R2)
- [ ] `overview.json` en 404, puis JSON invalide, puis `schema_version: 2` → message nommant le fichier, bandeau visible,
  aucune exception non interceptée. (R3)
- [ ] Fixture `empty` : l'Overview affiche « Aucune donnée disponible » ; fixture `m1` : leaderboard, signaux, KPIs et
  fiche signal en état vide, sélecteur de stratégie masqué. (R4)
- [ ] Le texte exact de P8 est présent sur chaque route, y compris les pages d'erreur et « Page introuvable ». (R5)
- [ ] `data_as_of` affiché sur chaque route ; horloge à `S' = data_as_of + 3` jours ouvrés → pas d'alerte, `+ 4` → «
  Données périmées (4 séances) » ; test unitaire du retard sur un week-end et un férié. (R6, R23)
- [ ] La bascule clair/sombre/système change les couleurs de la page et du graphique sans rechargement et survit à un
  rechargement ; « système » suit `prefers-color-scheme` émulé. (R7)
- [ ] `@axe-core/playwright` : aucune violation de contraste dans les deux thèmes ; bougies haussières creuses,
  marqueurs ▲ « BUY » / ▼ « SELL » ; navigation au clavier jusqu'au sélecteur de période. (R8)
- [ ] À 375 × 812, `scrollWidth <= 375` sur chaque route livrée. (R9)
- [ ] Build avec `TH_DASHBOARD_BASE=/TradingHelper/` servi sous ce chemin : Overview et Ticker chargent leurs données
  (aucune requête hors `/TradingHelper/`). (R10)
- [ ] Tests unitaires des formats : `232,40 $`, `0,1234 $`, `+0,63 %`, `23/11/2026`, `null` → `—` ; une date de séance
  reste la même dans les fuseaux `America/Los_Angeles` et `Pacific/Auckland`. (R11, R23)
- [ ] Fixture `m1` : une ligne par symbole avec sparkline SVG, benchmark signalé, clic → fiche ticker. (R12)
- [ ] `#/ticker/brk.b` résolu vers `BRK.B` (casse ignorée) ; `BRK%2DB` décodé en `BRK-B` (test unitaire) ; `#/ticker/ZZZ` → « Pas de données pour ZZZ ». (R14)
- [ ] Ticker de moins de 200 barres : SMA200 désactivée « historique insuffisant » ; aucune valeur de warm-up tracée à 0 ;
  SMA20 et SMA50 actives par défaut. (R15)
- [ ] Période 1M sur une fixture se terminant le 2026-11-23 → première barre ≥ 2026-10-23 ; 5A sur 2 ans d'historique →
  série complète ; défaut 6M. (R16, R23)
- [ ] Fixture `m1-signals` : sur AAPL, exactement deux marqueurs, BUY le 20/11/2026 et SELL le 23/11/2026, avec leur
  confiance ; aucun marqueur le 19/11 (HOLD) ; un marqueur à une date absente de la série n'est pas tracé et ne produit
  aucune erreur. (R17)
- [ ] `npm test` passe ; `pytest` valide chaque fichier de chaque fixture contre `schemas/`. (R23, R24)
- [ ] `npm run test:e2e` passe sur les fixtures `empty`, `m1` et `m1-signals`, sans erreur console ; le job `dashboard` de
  la CI exécute les deux suites. (R25)
- [ ] `npm run lighthouse` : performance ≥ 90 (médiane de 3) sur l'Overview mobile, moins de 5 Mo transférés. (R26)

### M3
- [ ] Fixture `m3` : KPIs renseignés, leaderboard contenant toutes les baselines présentes, signaux filtrables par
  stratégie, action et symbole, chacun avec confiance, modèle et `sharpe_oos`. (R13)
- [ ] Fixture `m3` : fiche signal du jour avec contributions de l'explication ; sans `explanation` → « Pas d'explication
  disponible ». Le détail d'un marqueur affiche `model_id` et `sharpe_oos`. (R17, R18)
- [ ] `#/portfolios` : une courbe par stratégie, première valeur à 100 chacune, baselines distinguées ; métriques
  identiques au fichier exporté. (R19, R23)
- [ ] `#/portfolio/<id>` : événement `model_switch` annoté à sa date, répartition sommant à 100 %, trades triés ;
  `#/portfolio/inconnu` → « Page introuvable ». (R20)
- [ ] `#/models` : boîtes à moustaches par métrique avec la position de chaque stratégie, model cards, calibration avec
  diagonale. (R21)
- [ ] `#/health` : ticker à `S' − 4` jours ouvrés → périmé (horloge injectée) ; section absente → « — » ; mention des
  avertissements tronqués. (R22)
- [ ] `npm run test:e2e` passe sur la fixture `m3` pour toutes les routes, à 375 px compris. (R9, R25)

## Hors périmètre
- Calcul d'indicateurs, de métriques ou de signaux côté client : tout vient de l'export (F08).
- Calendrier NYSE exact côté client (approximation jours ouvrés, Q2).
- Comparateur de tickers, simulateur « et si… », export CSV, page SHAP détaillée (backlog v2).
- Internationalisation (français seul), mode hors ligne / PWA, mise à jour intraday.
- Affichage d'un échec de `th validate` (non déployé, F08 Hors périmètre).
- Déploiement Pages et workflows (F10).

## Dépendances introduites (à justifier dans `plan.md`)
- `lightweight-charts` (dépendance, M1) : chandeliers, volume, overlays, marqueurs.
- `uplot` (dépendance, M3) : courbes d'equity, drawdown, calibration.
- `vitest` (devDependency) : tests unitaires de `lib/`.
- `@playwright/test` et `@axe-core/playwright` (devDependencies) : e2e, contraste.
- `lighthouse` (devDependency) : mesure R26 à la vérification.

## Pré-requis de contrat pour M3 (à régler dans F08 / §7 avant l'implémentation `[M3]`)
- Formats `portfolios/{strategy_id}.json` et `models.json` (déjà listés par F08) : ils DOIVENT fournir date de création,
  equity, drawdown, positions, trades, `model_switch` (date, ancien et nouveau `model_id`), métriques live, percentiles
  5/25/50/75/95 par métrique et calibration par décile, conformément à R19–R21.
- `health.json` : `runs` à étendre aux sections `signal` et `paper` (statut par étape, R22) quand F07 les définit.

## Décisions (validées le 2026-11-25)
- **Q1** Une seule spec, exigences et critères étiquetés `[M1]` / `[M3]`, comme F08 ; statut « ✔️ Done (M1) » possible
  avant M3.
- **Q2** Fraîcheur calculée dans le navigateur avec une approximation jours ouvrés (Définitions), sans modifier le
  contrat ; l'alerte globale porte sur `data_as_of` (le symbole le plus en retard), le détail par ticker est sur Health.
- **Q3** Distribution des random traders en boîtes à moustaches à partir des percentiles exportés (F05 R3, F08 R18) :
  pas d'histogramme, pas de modification de contrat.
- **Q4** Explication du signal du jour lue dans `overview.latest_signals` ; `tickers/*.json` n'est pas modifié.
- **Q5** Fixtures d'export commitées dans `dashboard/tests/fixtures/`, générées par `th export` et validées par `pytest`
  contre `schemas/` (le job `dashboard` n'a pas besoin de Python).
- **Q6** F09 écrit les tests Vitest et Playwright et les ajoute au job `dashboard` de `ci.yml` ; Lighthouse est mesuré à
  la vérification, pas en CI.
- **Q7** Sparklines en SVG inline sans bibliothèque (Overview légère pour Lighthouse).
- **Q8** Locale `fr-FR`, dates `JJ/MM/AAAA`, devise affichée en `$`.
- **Q9** Thème à trois états (clair, sombre, système par défaut), mémorisé dans `localStorage`.
- **Q10** Ticker : période par défaut 6M ; SMA20 et SMA50 actives, SMA200 et Bollinger inactives ; panneau RSI affiché.

## Questions ouvertes
Aucune.
