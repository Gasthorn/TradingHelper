# F01 — Ingestion quotidienne des cours (yFinance)

- **Statut** : 📝 Draft (revue du 2026-11-23 appliquée, en attente de validation)
- **Milestone** : M1
- **Dépend de** : F00
- **Contrats** : `03-data-contracts.md` §1, §2, §6
- **Principes clés** : P1 (pas de barre non clôturée), P5 (append-only, diffable, schémas), P6 (frugalité), P7 (robustesse source)

## Objectif
Récupérer les barres journalières OHLCV de tous les tickers de `config/universe.yaml` **et du benchmark** et les stocker
de façon incrémentale, atomique, idempotente et diffable dans `data/raw/prices/`.

## User stories
- En tant qu'owner, j'ajoute un ticker dans `universe.yaml` et, au prochain run, son historique complet depuis `start` est téléchargé.
- En tant qu'owner, je relance le téléchargement complet d'un ou plusieurs tickers (backfill / réparation) depuis une date donnée.
- En tant qu'owner, si le cron quotidien a raté plusieurs séances, le run suivant rattrape toutes les séances manquantes.

## Définitions
- **Dernière séance clôturée** `S` : plus grande séance NYSE `d` telle que `now_utc >= market_close(d) + 30 min`
  (calendrier NYSE, demi-séances comprises). `now_utc` est injectable.
- **Ticker tenté** : ticker pour lequel au moins un appel à la source a été fait pendant le run.
- **Tolérance de révision** `REVISION_TOL = 1e-4` (écart relatif, après arrondi à 4 décimales).

## Exigences

### Périmètre
- **R1** `th ingest` DOIT traiter tous les `tickers` de l'univers **et** le `benchmark` (décision F00 Q3). Le benchmark
  est ingéré comme un ticker ordinaire avec `start = min(start des tickers)` ; il n'est jamais tradé (hors F01).
  Un fichier de prix dont le symbole n'est plus dans l'univers n'est ni modifié ni supprimé.
- **R2** QUAND un ticker n'a pas de fichier, `th ingest` DOIT télécharger l'historique de `start` à `S` (mode initial).
  Le dossier `data/raw/prices/` est créé s'il n'existe pas. Une réponse vide en mode initial est un échec du ticker.
- **R3** QUAND un fichier existe et que sa dernière date est `>= S`, le ticker est « à jour » : aucun appel à la source.
  SINON, `th ingest` DOIT télécharger de `last_date − 5 séances NYSE` (incluse) à `S` (mode incrémental) :
  - les barres postérieures à `last_date` sont ajoutées (rattrapage de N séances possible) ;
  - une barre du recouvrement dont au moins une valeur diffère (après arrondi) est remplacée et comptée dans `bars_revised` ;
  - une barre stockée absente de la réponse est conservée et produit un avertissement ;
  - une réponse sans aucune barre postérieure à `last_date` est un échec du ticker (« aucune donnée pour des séances attendues »).

### Révisions d'historique
- **R4** QUAND, sur une barre du recouvrement, `close` **ou** `adj_close` diffère de plus de `REVISION_TOL` (split, dividende),
  le système DOIT re-télécharger l'historique complet du ticker depuis `min(start de l'univers, première date stockée)`,
  remplacer le fichier et positionner `history_rewritten: true` (avec `rewrite_reason`) pour ce ticker dans le rapport.
  Au plus une réécriture complète par ticker et par run. Si ce re-téléchargement échoue, l'ancien fichier est conservé
  intact et le ticker est en échec. La journalisation explicite exigée par P5 est assurée par le rapport et par le message
  de commit (F10 R2).

### Contenu et nettoyage des barres
- **R5** Les barres DOIVENT être demandées avec `auto_adjust=False` : `open`, `high`, `low`, `close` sont ajustés des
  **splits uniquement** (comportement yfinance) ; `adj_close` est ajusté des splits **et** des dividendes. Les prix sont
  arrondis à 4 décimales, le volume est un entier. Les dates sont converties en `datetime.date` de séance (fuseau supprimé).
- **R6** Avant écriture, le système DOIT écarter, avec un avertissement (ticker + date + règle) dans le rapport, toute barre :
  contenant une valeur manquante (NaN) ; datée d'un jour qui n'est pas une séance NYSE ou postérieure à `S` ;
  avec un prix `<= 0` ou un volume `< 0` ; violant `low <= min(open, close)` ou `high >= max(open, close)` après arrondi.
  Les dates dupliquées dans une réponse sont dédoublonnées (dernière occurrence conservée). Un volume nul est conservé
  (avertissement F02). Ainsi un fichier écrit par F01 respecte toujours les règles bloquantes de F02 R2.

### Écriture
- **R7** Le système NE DOIT écrire aucune barre pour une séance postérieure à `S` (marché non clôturé, y compris demi-séances).
- **R8** Chaque fichier DOIT être écrit de manière atomique (fichier temporaire dans le même dossier + `os.replace`, via
  `storage`), selon la **sérialisation canonique** du contrat §2. `last_updated` ne change que si `bars` change ;
  un fichier dont le contenu ne change pas n'est pas réécrit.
- **R9** QUAND un fichier existant est illisible ou non conforme au schéma `prices`, le système NE DOIT PAS l'écraser :
  le ticker est en échec avec un message invitant à lancer `th ingest --symbols X --full`.

### Robustesse de la source
- **R10** Chaque appel à la source DOIT être retenté en cas d'erreur (y compris limitation de débit) : 1 tentative +
  3 relances, avec attentes de 2 s, 4 s et 8 s (fonction `sleep` injectable). Un ticker en échec n'interrompt pas les autres.
- **R11** Les téléchargements DOIVENT être regroupés par lots de ≤ 20 tickers partageant la même date de début.
  Un ticker absent ou entièrement vide dans la réponse d'un lot est retenté **individuellement** selon R10.
- **R12** Le symbole de config est converti pour yfinance en remplaçant `.` par `-` (ex. `BRK.B` → `BRK-B`) ;
  le fichier et le champ `symbol` gardent le symbole de config.

### CLI
- **R13** `th ingest [--symbols A,B] [--full] [--start YYYY-MM-DD]` :
  - `--symbols` restreint le run aux symboles listés, qui DOIVENT appartenir à l'univers ou être le benchmark ;
  - `--full` re-télécharge tout l'historique des symboles concernés depuis `--start` (défaut : `start` de l'univers)
    et remplace leur fichier (`history_rewritten: true`, `rewrite_reason: "backfill"`) ;
  - `--start` sans `--full`, une date invalide ou future, ou un symbole inconnu → message sur stderr, code 2, aucun appel réseau.
- **R14** Codes de sortie : **2** erreur de config (F00 R10) ou d'arguments ; **1** si au moins un ticker a été tenté et que
  **tous** les tickers tentés ont échoué ; **0** sinon (y compris aucun ticker à tenter).

### Rapport et contrats
- **R15** QUAND au moins un fichier de prix a été modifié ou au moins un ticker a échoué, le système DOIT ajouter une
  entrée à la section `ingest` de `data/runs/{S}.json` (contrat §6) — sans modifier les autres sections — avec, par ticker :
  statut, mode, barres ajoutées, barres révisées, `history_rewritten`, nombre de tentatives, erreur ; et pour le run :
  début, fin, durée, `S`, code de sortie, avertissements. Sinon (ex. jour férié, 2e run) aucun fichier n'est écrit et un
  résumé est affiché sur stdout.
- **R16** Le code d'accès à yfinance DOIT être isolé derrière une interface `PriceSource` ; l'horloge (`now_utc`) et
  `sleep` DOIVENT être injectables. Aucun appel réseau dans `pytest` (`FakePriceSource`).
- **R17** Les modèles `PricesFile` et `RunReport` (section `ingest`) DOIVENT être définis dans `schemas.py` ; F01 crée la
  commande `th schemas` (sans config requise) qui génère `schemas/prices.schema.json` et `schemas/run_report.schema.json`.
  Le contrôle de synchronisation en CI reste dans F02 R6.

## Critères d'acceptation
- [ ] Avec une `FakePriceSource` et sans `data/raw/prices/`, un run initial crée un fichier par ticker + `SPY.json`, conformes au JSON Schema `prices` et à la sérialisation canonique. (R1, R2, R8, R17)
- [ ] Ajouter un ticker à l'univers → son fichier est créé depuis `start`, les autres fichiers ne changent pas. (R2, R3)
- [ ] Un 2e run pour la même `S` ne fait aucun appel à la source et ne modifie aucun fichier (`git diff` vide, pas de rapport écrit). (R3, R8, R15)
- [ ] Un run après une nouvelle séance ajoute exactement 1 ligne par ticker ; après 3 séances manquées, exactement 3 lignes. (R3)
- [ ] Une barre du recouvrement modifiée sur le volume seul est remplacée (`bars_revised = 1`) sans réécriture complète. (R3)
- [ ] Une révision simulée d'`adj_close` de 0,3 % (dividende) déclenche une réécriture complète et `history_rewritten: true`. (R4)
- [ ] Un échec du re-téléchargement complet laisse l'ancien fichier identique octet pour octet. (R4, R8)
- [ ] Une réponse contenant NaN, un week-end, une date dupliquée et `high < low` : seules les barres valides sont écrites, avertissements listés. (R5, R6)
- [ ] `now_utc` = 15 h ET un jour de séance → pas de barre du jour ; 27/11/2026 13 h 45 ET (demi-séance) → barre écrite. (R7)
- [ ] Une exception simulée pendant l'écriture laisse le fichier d'origine intact. (R8)
- [ ] Un fichier existant corrompu n'est pas écrasé ; ticker en échec avec message `--full`. (R9)
- [ ] Source échouant 2 fois puis réussissant → ticker OK, attentes 2 s et 4 s observées ; 4 échecs → ticker KO, attentes 2, 4, 8 s. (R10)
- [ ] 45 tickers de même date de début → 3 appels par lot ; un ticker vide dans un lot est retenté seul. (R11)
- [ ] `BRK.B` est demandé à la source en `BRK-B` et stocké dans `BRK.B.json`. (R12)
- [ ] `th ingest --symbols AAPL --full --start 2015-01-01` ne réécrit que `AAPL.json`, qui commence à la 1re séance ≥ 2015-01-01. (R13)
- [ ] `--start` sans `--full`, symbole inconnu → code 2, aucun appel à la source. (R13, R14)
- [ ] Une exception sur 1 ticker sur 3 : les 2 autres sont écrits, code 0, ticker en erreur listé dans le rapport. (R10, R14, R15)
- [ ] Tous les tickers tentés en échec → code 1. (R14)
- [ ] Un run un jour férié NYSE ne fait aucun appel et ne produit aucun changement. (R3, R15)
- [ ] Le rapport respecte le JSON Schema `run_report` ; une 2e entrée `ingest` (backfill) s'ajoute sans effacer la 1re ni les autres sections. (R15, R17)

## Dépendances introduites (à justifier dans `plan.md`)
`yfinance`, `pandas`, `pandas_market_calendars` (calendrier NYSE avec demi-séances, cf. `02-architecture.md`).

## Décisions (revue du 2026-11-23, à valider)
- **Q1** Rapport de run : schéma `RunReport` dans `schemas.py` ; nommé d'après `S` ; chaque commande met à jour sa seule section ; `ingest` est une liste d'exécutions ; non écrit s'il n'y a rien à signaler (R15).
- **Q2** Seuil de révision : tolérance quasi nulle `1e-4` sur `close` et `adj_close` (au lieu de 0,5 % sur `adj_close`), pour capter tous les dividendes et garder un facteur `adj_close/close` cohérent (R4).
- **Q3** Réécriture et P5 : journalisée dans le rapport et dans le message de commit (F10 R2), pas d'ADR.
- **Q4** Backfill : symboles de l'univers ou benchmark uniquement ; `--full` + `--start` optionnel ; pas de `--end` (évite les trous) (R13).
- **Q5** Barres invalides : écartées par F01 avec avertissement, pour qu'un ticker isolé ne bloque pas tout le daily via F02 R4 (R6).
- **Q6** Benchmark : `start = min(start des tickers)`, traité comme un ticker (R1).
- **Q7** Dépendances : voir section ci-dessus.
- **Q8** Colonnes : `auto_adjust=False` ; OHLC ajustés des splits, `adj_close` ajusté splits + dividendes ; les features calculent le facteur `adj_close/close` (R5, contrat §2).

## Questions ouvertes
Aucune.
