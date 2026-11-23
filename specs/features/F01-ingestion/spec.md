# F01 — Ingestion quotidienne des cours (yFinance)

- **Statut** : 📝 Draft
- **Milestone** : M1
- **Dépend de** : F00
- **Contrats** : `03-data-contracts.md` §1, §2, §6

## Objectif
Récupérer les barres journalières OHLCV de tous les tickers de `config/universe.yaml` et les stocker
de façon incrémentale, atomique et diffable dans `data/raw/prices/`.

## User stories
- En tant qu'owner, j'ajoute un ticker dans `universe.yaml` et, au prochain run, son historique complet depuis `start` est téléchargé.
- En tant qu'owner, je lance un backfill manuel d'un ticker sur une période donnée.

## Exigences
- **R1** `th ingest` DOIT, pour chaque ticker, ne télécharger que les séances postérieures à la dernière barre stockée (mode incrémental), avec un recouvrement de 5 séances pour détecter les révisions.
- **R2** QUAND un ticker n'a pas de fichier, `th ingest` DOIT télécharger l'historique depuis `start` (mode initial).
- **R3** QUAND les barres de recouvrement diffèrent de > 0,5 % sur `adj_close` (split/dividende), le système DOIT re-télécharger l'historique complet du ticker et positionner `history_rewritten: true` dans le rapport.
- **R4** Le système DOIT écrire chaque fichier de manière atomique (fichier temporaire + `os.replace`).
- **R5** Le système DOIT retenter un ticker en échec 3 fois avec backoff exponentiel (2 s, 4 s, 8 s) ; un ticker en échec n'interrompt pas les autres.
- **R6** Le système DOIT regrouper les téléchargements (`yf.download` multi-tickers par lots de 20) pour limiter les appels.
- **R7** Le système NE DOIT PAS écrire de barre pour la séance du jour si le marché n'est pas encore clôturé (calendrier NYSE).
- **R8** `th ingest --symbols AAPL,MSFT --start 2015-01-01 --full` DOIT permettre un backfill ciblé.
- **R9** Le système DOIT produire `data/runs/{date}.json` (section `ingest`) : tickers OK/KO, barres ajoutées, révisions, durée.
- **R10** Le code d'accès à yfinance DOIT être isolé derrière une interface `PriceSource` pour être mocké en test (aucun appel réseau dans `pytest`).
- **R11** Code de sortie : 0 si ≥ 1 ticker mis à jour ou aucune nouvelle séance ; 1 si **tous** les tickers échouent.

## Critères d'acceptation
- [ ] Avec une `FakePriceSource`, un run initial crée un fichier conforme au JSON Schema `prices`.
- [ ] Un 2e run le même jour ne modifie aucun fichier (idempotence, `git diff` vide).
- [ ] Un run après une nouvelle séance ajoute exactement 1 ligne par ticker.
- [ ] Une révision simulée d'`adj_close` déclenche une réécriture complète et `history_rewritten: true`.
- [ ] Une exception sur 1 ticker sur 3 : les 2 autres sont écrits, code de sortie 0, ticker en erreur listé.
- [ ] Un run un jour férié NYSE ne produit aucun changement.

## Questions ouvertes
- Stocker `adj_close` seul ou OHLC ajustés ? → v1 : OHLC bruts + `adj_close` ; les features calculent un facteur d'ajustement `adj_close/close`.
