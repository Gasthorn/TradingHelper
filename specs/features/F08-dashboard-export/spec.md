# F08 — Export des données pour le dashboard

- **Statut** : 🧭 Planned (M1, 2026-11-24) — M3 : ✅ Approved, plan à compléter
- **Milestone** : M1 (partiel : exigences et critères `[M1]`) puis M3 (complet : `[M3]`)
- **Dépend de** : F01, F02 (M1) ; F04–F07 pour les sections `[M3]`
- **Contrats** : `03-data-contracts.md` §7 (production) ; §1, §2, §6 (lecture) ; §3, §4, §5 (lecture, M3)
- **Principes clés** : P1 (indicateurs sur fenêtres passées), P3 (baselines toujours exportées), P5 (export validé par schéma, non commité), P6 (temps d'export), P8 (signal = confiance + modèle + performance)

## Objectif
Transformer les données du dépôt (prix bruts, rapports de run, puis signaux, portefeuilles et registre) en fichiers JSON
compacts, pré-calculés, validés par schéma et optimisés pour le navigateur, que le dashboard statique (F09) charge à la demande.

## User stories
- En tant que visiteur, j'ouvre le dashboard et la page d'accueil se charge vite, sans télécharger l'historique de chaque ticker.
- En tant que visiteur, je vois sur la fiche d'un ticker les chandeliers, SMA, Bollinger, RSI et les signaux BUY/SELL des stratégies.
- En tant qu'owner, je vois la fraîcheur des données et l'état des derniers runs sur la page Health.
- En tant qu'owner, je lance `th export` en local après un `th ingest` et j'obtiens exactement ce que la CI publiera.

## Définitions
- **`S`** : dernière séance clôturée, définie par F01 (même fonction, `now_utc` injectable).
- **Symboles exportés** : les `tickers` de l'univers et le `benchmark` qui disposent d'un fichier de prix. Les fichiers
  orphelins (symbole retiré de l'univers, conservés par F01 R1) ne sont pas exportés.
- **`data_as_of`** : la plus petite dernière date parmi les symboles exportés (vue prudente : toutes les séries sont à jour
  au moins jusqu'à cette date) ; `null` s'il n'y a aucun symbole exporté.
- **Grille d'arrondi** : prix et indicateurs de prix (OHLC, SMA, Bollinger, `last_close`, sparklines) à **4 décimales** ;
  RSI à **2 décimales** ; ratios, rendements, poids, confiances et métriques à **4 décimales** ; montants (equity, cash) à
  **2 décimales** ; volumes et quantités en **entiers**. Les flottants sont écrits sous leur représentation la plus courte.
- **Fichier source** : tout fichier lu par l'export (`data/raw/prices/*.json`, `data/runs/*.json`, puis `data/signals/*.json`,
  `data/portfolios/*.json`, `models/registry/**`), sous `TH_DATA_DIR` pour ce qui relève de `data/`.

## Exigences

### Commande et sortie
- **R1** `[M1]` `th export [--out DIR]` (défaut : `dashboard/public/data`) DOIT produire les fichiers du contrat §7
  disponibles au milestone courant, chacun conforme à son modèle pydantic. L'export n'effectue aucun appel réseau et ne
  modifie aucun fichier source.
- **R2** `[M1]` L'export DOIT reconstruire DIR entièrement : les fichiers sont écrits dans un dossier temporaire voisin,
  qui remplace DIR à la fin. Aucun fichier d'un export précédent ne subsiste (ex. ticker retiré de l'univers) ; en cas
  d'échec, DIR reste dans son état antérieur et le dossier temporaire est supprimé.
- **R3** `[M1]` Codes de sortie : **2** erreur de config (F00 R10) ou d'arguments ; **1** fichier source illisible ou non
  conforme à son schéma (rien n'est écrit dans DIR, chaque fichier fautif est cité sur stderr) ; **0** sinon. Un résumé
  (fichiers produits, tailles, `data_as_of`) est affiché sur stdout.
- **R4** `[M1]` Les modèles des fichiers d'export (`ManifestFile`, `TickerFile`, `OverviewFile`, `HealthFile`, puis
  `PortfolioExportFile` et `ModelsFile` en M3) DOIVENT être définis dans `schemas.py` ; `th schemas` DOIT générer les
  `schemas/*.schema.json` correspondants (synchronisation contrôlée par le test existant, F01 R17).
- **R5** `[M1]` Le dashboard DOIT disposer de types TypeScript générés depuis `schemas/*.schema.json`
  (`json-schema-to-typescript`, script `npm run gen:types` vers `dashboard/src/types/`), commités, et la CI DOIT échouer
  si leur régénération produit un diff.

### Fiche ticker
- **R6** `[M1]` `tickers/{SYMBOL}.json` DOIT être produit pour chaque symbole exporté, benchmark compris, au format
  colonnes (un tableau par colonne, tous de même longueur) : `date`, `open`, `high`, `low`, `close` (ajustés des splits,
  tels que stockés, alignés avec les chandeliers), `volume`, `sma20`, `sma50`, `sma200`, `bb_upper`, `bb_lower`, `rsi14`.
  Le milieu de Bollinger n'est pas exporté (égal à `sma20`).
- **R7** `[M1]` F08 DOIT créer `features/indicators.py` (fonctions pures, `numpy` uniquement), qui sera repris et étendu
  par F03 : `sma(x, n)` ; `bollinger(x, n=20, k=2)` avec écart-type de population (`ddof=0`) ; `rsi_wilder(x, n=14)`
  (première moyenne = moyenne simple des `n` premières variations, puis lissage de Wilder ; perte moyenne nulle → 100 ;
  gain et perte moyens nuls → 50). Les indicateurs sont calculés sur `close`.
- **R8** `[M1]` Un indicateur à l'index `t` NE DOIT dépendre que des valeurs d'index `<= t` (fenêtres glissantes passées,
  P1). Tant que la fenêtre est incomplète (warm-up), la valeur est `null` ; aucune valeur `NaN` ou infinie n'est écrite.
- **R9** `[M1]` `tickers/{SYMBOL}.json` DOIT contenir `markers` : les signaux **BUY** et **SELL** de ce symbole lus dans
  `data/signals/{YYYY-MM-DD}.json` (hors `latest.json`), chacun avec `date`, `strategy_id`, `action`, `confidence`, triés
  par date puis `strategy_id`. Les HOLD sont exclus. Sans dossier `data/signals/` (M1), `markers` est une liste vide.

### Accueil, manifest, santé
- **R10** `[M1]` `overview.json` DOIT contenir, pour chaque symbole exporté, `last_close`, `change_1d` (rendement simple
  de la dernière séance, `null` si une seule barre) et `spark` (les 60 dernières clôtures au plus), afin que la page
  Overview ne charge aucun fichier `tickers/*`. Il contient aussi `leaderboard`, `latest_signals` et `kpis` (R16).
- **R11** `[M1]` `manifest.json` DOIT contenir `schema_version`, `generated_at` (UTC ISO-8601, horloge injectable),
  `data_as_of`, `git_sha` (`GITHUB_SHA` s'il est défini, sinon `git rev-parse HEAD`, sinon `null`), `currency`,
  `benchmark`, `tickers` (symbole, nom, secteur — pour le benchmark, nom = symbole et secteur `null` —,
  `benchmark: bool`, première et dernière date), `strategies` (vide en M1)
  et `files` : pour chaque autre fichier produit, `path` relatif à DIR, `sha256` (16 premiers caractères hexadécimaux du
  hash des octets) et `bytes`, triés par `path`. Le front ajoute `?v=<sha256>` aux URL (cache-busting).
- **R12** `[M1]` `health.json` DOIT contenir :
  - `last_session` : `S` au moment de l'export ;
  - `tickers` : pour chaque symbole de l'univers et le benchmark, `last_date`, `sessions_behind` (séances NYSE entre
    `last_date` et `S`) et `stale` (même définition que F02 : `last_date < S − 3 séances`) ; sans fichier de prix,
    `last_date` et `sessions_behind` valent `null` et `stale` vaut `true` ;
  - `runs` : les 10 rapports `data/runs/*.json` les plus récents (par `session_date` décroissante), résumés par section
    à partir de la **dernière** exécution de chaque section : `ingest` (`exit_code`, nombre de tickers `ok`, `unchanged`,
    `failed`, symboles avec `history_rewritten`) et `validate` (`exit_code`, nombre de violations et d'avertissements),
    `null` pour une section absente ;
  - `quality_warnings` : les avertissements de la dernière exécution `validate` du rapport le plus récent qui en a une,
    limités à 100, avec `quality_warnings_truncated` (nombre d'avertissements omis).

### Sections dépendant de features ultérieures
- **R13** `[M1]` QUAND les fichiers source d'une section n'existent pas (`data/signals/`, `data/portfolios/`,
  `models/registry/` absents), l'export DOIT produire cette section vide (listes vides, `null` pour les valeurs uniques)
  et réussir. QUAND un fichier source existe mais est illisible ou non conforme à son schéma, l'export DOIT échouer (R3)
  plutôt que masquer l'erreur (P5).

### Format
- **R14** `[M1]` Tous les nombres DOIVENT respecter la grille d'arrondi ; le JSON DOIT être minifié (séparateurs `,` et `:`,
  sans espace hors des chaînes), en UTF-8, avec un champ `schema_version` dans chaque fichier.
- **R15** `[M1]` À fichiers source, horloge et `git_sha` identiques, deux exports DOIVENT produire des fichiers identiques
  octet pour octet (aucun ordre dépendant d'un dictionnaire ou du système de fichiers).

### Compléments M3
- **R16** `[M3]` `overview.json` DOIT contenir `leaderboard` (une ligne par stratégie ayant un portefeuille : `strategy_id`,
  `kind` ∈ {`baseline`, `model`}, `equity`, `return_30d`, `sharpe_oos`, `random_percentile`), `latest_signals` (contenu de
  `data/signals/latest.json`, chaque signal enrichi de `model_id` et `sharpe_oos` de sa stratégie) et `kpis`
  (`best_strategy_30d`). Les baselines présentes (`buy_hold`, `buy_hold_spy`, `random_s42`, `sma_cross`) DOIVENT toujours
  figurer dans `leaderboard` et dans `models.json` (P3). Le manifest liste les stratégies (`id`, `kind`, `model_id` du
  champion pour une famille ML, `sharpe_oos`), ce qui permet au front d'afficher modèle et performance de chaque marqueur (P8).
- **R17** `[M3]` `portfolios/{strategy_id}.json` DOIT contenir la courbe d'equity, la courbe de drawdown, les positions,
  les trades, les événements `model_switch` et les métriques live calculées par `backtest/metrics.py` (aucun calcul de
  métrique dupliqué dans `export/`).
- **R18** `[M3]` `models.json` DOIT contenir les model cards (contrat §5), les métriques OOS, la distribution des random
  traders (percentiles 5/25/50/75/95 par métrique, F05 R3) et les courbes de calibration par décile (F06 R3).

### Performance
- **R19** `[M1]` Pour 20 tickers × 15 ans (≈ 3 780 séances), l'export DOIT durer moins de 30 s et chaque fichier DOIT
  respecter la taille cible du contrat §7.

## Critères d'acceptation

### M1
- [ ] Dépôt avec seulement des prix et des rapports de run (fixtures) : `th export` → code 0, fichiers `manifest`,
  `overview`, `health`, `tickers/*` (benchmark compris) produits ; `markers`, `leaderboard`, `latest_signals`,
  `strategies` vides ; aucun fichier `portfolios/` ni `models.json` requis. (R1, R6, R13)
- [ ] Chaque fichier produit est validé par son modèle pydantic **et** par son JSON Schema (`jsonschema`, Draft 2020-12) ;
  `schemas/` est synchronisé (`test_generated_schemas_match_committed`). (R1, R4)
- [ ] `npm run gen:types` ne produit aucun diff et `npm run typecheck` passe avec les types générés. (R5)
- [ ] Un fichier `tickers/OLD.json` présent dans `--out` a disparu après l'export ; une exception simulée en cours
  d'export laisse `--out` identique et ne laisse pas de dossier temporaire. (R2)
- [ ] Un fichier de prix corrompu → code 1, fichier cité sur stderr, `--out` inchangé ; erreur de config ou argument
  invalide → code 2 ; `--out` personnalisé et `TH_DATA_DIR` respectés. (R3)
- [ ] SMA20/50/200, Bollinger(20, 2) et RSI14 comparés à des valeurs de référence calculées à la main / au tableur sur une
  fixture, à 1e-4 près ; série plate → RSI 50 ; série strictement croissante → RSI 100. (R7)
- [ ] Le nombre de `null` de warm-up est exact (19, 49, 199, 19, 14) ; un ticker de moins de 200 barres a `sma200`
  entièrement `null` ; aucun `NaN` dans la sortie. (R8, R14)
- [ ] Test de propriété (hypothesis) : pour tout `t`, les indicateurs à `t` calculés sur la série tronquée à `t` sont égaux
  à ceux calculés sur la série complète. (R8)
- [ ] Avec une fixture `data/signals/` (BUY le 2026-11-20, HOLD le 2026-11-21, SELL le 2026-11-23 sur AAPL),
  `tickers/AAPL.json` contient exactement les marqueurs BUY et SELL aux bonnes dates avec leur confiance. (R9)
- [ ] `overview.json` contient `spark` de 60 valeurs (moins pour un historique court) et `change_1d` correct. (R10)
- [ ] Le `sha256` et les `bytes` de chaque fichier du manifest correspondent aux fichiers réels ; `git_sha` vaut
  `GITHUB_SHA` s'il est défini et `null` hors dépôt git ; `data_as_of` vaut la date du symbole le plus en retard. (R11)
- [ ] `health.json` : symbole de l'univers sans fichier → `last_date: null`, absent de `tickers/` et du manifest ;
  ticker à `S − 4 séances` → `stale: true` (`now_utc` injecté) ; 12 rapports → 10 résumés, triés ; 150 avertissements →
  100 conservés, `quality_warnings_truncated: 50`. (R12)
- [ ] Un fichier orphelin de `data/raw/prices/` n'est pas exporté. (Définitions)
- [ ] Aucun flottant ne dépasse les décimales de sa catégorie (NVDA 2010 à ~0,1 $ garde 4 décimales) ; aucun espace hors
  des chaînes. (R14)
- [ ] Deux exports sur les mêmes fixtures avec horloge et `git_sha` figés → fichiers identiques (SHA-256). (R15)
- [ ] Fixture synthétique seedée de 20 tickers × 15 ans : chaque fichier sous sa taille cible, export < 30 s. (R19)
- [ ] Aucun fichier source modifié (empreintes identiques) et aucun appel réseau (`pytest-socket`). (R1)

### M3
- [ ] Avec portefeuilles, signaux et registre en fixtures : `leaderboard` contient toutes les baselines présentes,
  `latest_signals` porte `model_id` et `sharpe_oos`, le manifest liste les stratégies. (R16)
- [ ] `portfolios/{id}.json` : drawdown et métriques identiques à `backtest/metrics.py` sur la même courbe ; événements
  `model_switch` présents. (R17)
- [ ] `models.json` contient model cards, distribution des random traders et calibration, valide son schéma. (R18)
- [ ] Fixture 20 tickers × 15 ans avec portefeuilles et modèles : tailles cibles respectées. (R19)

## Hors périmètre
- Rendu et logique d'affichage (F09) ; déclenchement en CI et déploiement (F10).
- Export incrémental : l'export recalcule tout à chaque run (une réécriture d'historique F01 R4 est donc prise en compte
  sans traitement particulier).
- Marqueurs issus des backtests historiques : seuls les signaux live sont marqués (les trades figurent dans `portfolios/`).
- Affichage d'un échec de `th validate` sur le site : F10 ne déploie pas dans ce cas et le rapport n'est pas commité,
  donc `health.json` ne le montre pas (il est visible dans l'artefact du workflow).
- Re-validation des règles qualité F02 : l'export ne vérifie que la conformité au schéma.

## Dépendances introduites (à justifier dans `plan.md`)
- `numpy` déclaré en dépendance directe (aujourd'hui transitive via pandas) pour `features/indicators.py`.
- `json-schema-to-typescript` (devDependency du dashboard) pour R5.

## Pré-requis de contrat pour M3 (à régler dans les specs concernées avant l'implémentation M3)
- §3 / F07 : ajouter au portefeuille les événements `model_switch` (F07 R4) et `pending_orders` (F07 R6).
- §5 / F06 : stocker la calibration par décile (F06 R3) dans `model_card.json` (ou un fichier voisin).
- F05 R3 : définir l'emplacement et le format de la distribution des random traders.
- §7 : détailler les formats `portfolios/{strategy_id}.json` et `models.json` une fois ces points réglés.

## Décisions (2026-11-24, à valider avec la spec)
- **Q1** Indicateurs en M1 : F08 crée `features/indicators.py` (SMA, Bollinger, RSI) en `numpy` pur ; F03 le reprend et
  l'étend, sans duplication (R7).
- **Q2** Marqueurs : signaux live BUY/SELL uniquement, lus dans `data/signals/` ; HOLD exclus (R9).
- **Q3** Arrondi : grille des Définitions ; 4 décimales pour les prix car les cours anciens ajustés des splits peuvent
  valoir moins de 1 $ (R14).
- **Q4** `data_as_of` = minimum des dernières dates des symboles exportés (Définitions).
- **Q5** `health.json` : 10 derniers rapports, 100 avertissements au plus ; `overview.json` : sparklines de 60 clôtures (R10, R12).
- **Q6** Fichier source absent → section vide ; fichier source invalide → échec en code 1 (R3, R13).
- **Q7** Une seule spec, exigences et critères étiquetés `[M1]`/`[M3]` ; statut « ✔️ Done (M1) » possible avant M3.
- **Q8** Les trous de contrat M3 (§3, §5, F05) sont listés comme pré-requis, pas résolus dans F08.
- **Q9** Génération des types TS portée par F08 (le contrat et son critère d'acceptation lui appartiennent) (R5).

## Questions ouvertes
Aucune pour M1. Les points M3 sont listés dans « Pré-requis de contrat pour M3 ».
