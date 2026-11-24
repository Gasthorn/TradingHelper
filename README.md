# TradingHelper

> **Outil expérimental et éducatif. Ceci n'est pas un conseil en investissement.**

Outil d'aide au trading **100 % GitHub** : GitHub Actions récupère chaque soir de bourse les cours
journaliers (yFinance), entraîne et évalue des stratégies (baselines et modèles d'IA) face au hasard
et au Buy & Hold, fait vivre des portefeuilles fictifs, et publie un dashboard statique sur GitHub Pages.
Aucun ordre réel n'est jamais passé.

Le projet est développé en **Spec-Driven Development** : voir [`specs/`](specs/README.md),
la [constitution](specs/00-constitution.md) et la [roadmap](specs/roadmap.md).

## Installation

Prérequis :
- [uv](https://docs.astral.sh/uv/) : il installe lui-même Python 3.12 (fixé par `.python-version`) ;
- Node.js 22 LTS pour le dashboard (fixé par `dashboard/.nvmrc`). Si une autre version de Node est déjà
  installée, utiliser un gestionnaire de versions comme [fnm](https://github.com/Schniz/fnm) :
  `fnm install 22`, puis `fnm use` dans `dashboard/`.

```bash
uv sync                                   # dépendances Python (verrouillées par uv.lock)
cd dashboard && npm ci                    # dépendances du dashboard (verrouillées par package-lock.json)
```

Vérifier l'installation :

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/ && uv run pytest
cd dashboard && npm run lint && npm run typecheck && npm run build && npm run check:dist
```

## Commandes `th`

La CLI `th` expose une commande par étape du pipeline. Les commandes disponibles aujourd'hui :

| Commande | Effet |
|---|---|
| `uv run th --help` | Liste les commandes. |
| `uv run th version` | Affiche la version du package (`tradinghelper X.Y.Z`). |
| `uv run th ingest` | Télécharge les cours journaliers (yfinance) de l'univers et du benchmark. |
| `uv run th validate` | Vérifie les fichiers de prix (règles bloquantes et avertissements), sans les modifier. |
| `uv run th schemas` | Régénère les JSON Schemas de `schemas/` depuis `src/tradinghelper/schemas.py`. |

Les étapes suivantes (`th export`…) arrivent avec les features F08 et au-delà.

### `th ingest`

Télécharge les barres journalières OHLCV de tous les tickers de `config/universe.yaml` et du benchmark
dans `data/raw/prices/{SYMBOLE}.json` (une barre par ligne, format canonique du
[contrat §2](specs/03-data-contracts.md)).

- **Premier run** : historique complet depuis le `start` de chaque ticker (le benchmark démarre au plus
  ancien `start`).
- **Runs suivants** : seules les séances manquantes sont téléchargées, avec un recouvrement de 5 séances
  pour détecter les révisions. Un split ou un dividende qui modifie l'historique ajusté déclenche une
  réécriture complète du fichier, signalée dans le rapport (`history_rewritten`).
- Seules les séances NYSE clôturées depuis au moins 30 minutes sont écrites (demi-séances comprises).
- Un ticker à jour ne déclenche aucun appel réseau : relancer `th ingest` est sans effet.

```bash
uv run th ingest                                          # run quotidien
uv run th ingest --symbols AAPL,MSFT                      # seulement ces symboles
uv run th ingest --symbols AAPL --full                    # re-télécharge tout l'historique d'AAPL
uv run th ingest --symbols AAPL --full --start 2015-01-01 # backfill depuis une date
```

`--full` **remplace** le fichier depuis `--start` (défaut : `start` de l'univers) ; c'est aussi le moyen
de réparer un fichier corrompu, qu'un run ordinaire refuse d'écraser. Attention : un `--start` postérieur
au début actuel du fichier tronque l'historique.

Codes de sortie :

| Code | Signification |
|---|---|
| `0` | Au moins un ticker mis à jour, ou rien à faire (jour férié, déjà à jour). |
| `1` | Tous les tickers tentés ont échoué. |
| `2` | Configuration ou arguments invalides (aucun appel réseau n'est fait). |

Quand un fichier a été modifié ou qu'un ticker a échoué, `th ingest` ajoute une entrée à la section
`ingest` du rapport `data/runs/{AAAA-MM-JJ}.json`, nommé d'après la dernière séance clôturée
([contrat §6](specs/03-data-contracts.md)). Un run sans rien à signaler n'écrit aucun rapport.

Le dossier de données est `data/` à la racine du dépôt, ou celui indiqué par la variable
d'environnement `TH_DATA_DIR`.

### `th validate`

Vérifie chaque fichier de `data/raw/prices/` **sans le modifier** et sans appel réseau, avant que les
données n'alimentent les modèles.

- **Règles bloquantes** (sur tout l'historique) : fichier illisible ou non conforme au
  [contrat §2](specs/03-data-contracts.md), symbole différent du nom du fichier, fichier vide, dates non
  strictement croissantes, date hors séance NYSE ou postérieure à la dernière séance clôturée, prix `<= 0`
  ou non fini, prix non arrondi à 4 décimales, volume négatif, `low`/`high` incohérents avec `open`/`close`.
  Toutes les violations sont listées sur stderr, une par ligne : `SYMBOLE DATE règle: détail`.
- **Avertissements** (n'arrêtent rien) : séances manquantes (regroupées en plages), variation journalière de
  plus de 40 % (en log-rendement, soit +40 % ou −28,6 %), volume nul, fichier périmé (dernière barre
  antérieure à 3 séances), symbole de l'univers sans fichier. Les trois premiers ne portent que sur les
  10 dernières séances, sauf avec `--all-history`.
- Un fichier dont le symbole n'est plus dans l'univers n'est soumis qu'aux règles bloquantes.

```bash
uv run th validate                       # run quotidien (après th ingest)
uv run th validate --symbols AAPL,MSFT   # seulement ces fichiers (les autres sont ignorés)
uv run th validate --all-history         # avertissements sur tout l'historique (audit)
```

Codes de sortie :

| Code | Signification |
|---|---|
| `0` | Aucune règle bloquante violée (avertissements possibles, ou aucun fichier de prix). |
| `1` | Au moins une règle bloquante violée : le daily ne commite pas (F10). |
| `2` | Configuration ou arguments invalides. |

`th validate` ajoute une entrée à la section `validate` du rapport `data/runs/{AAAA-MM-JJ}.json` si ce rapport
existe déjà (écrit par `th ingest` le même jour) ou s'il y a une violation ; sinon (jour férié, 2e run) il
n'écrit aucun rapport. Un rapport existant illisible n'est jamais écrasé. Pour réparer un fichier en
violation : `uv run th ingest --symbols X --full`.

### Configuration

Toute commande (sauf `th schemas`) charge et valide `config/universe.yaml`, `config/backtest.yaml` et `config/strategies.yaml`.
Une configuration invalide arrête `th` avec le code de sortie **2** et un message indiquant
le fichier, le champ et la raison, par exemple :

```
Erreur de configuration : config/universe.yaml: tickers: symbole dupliqué 'AAPL' (positions 0 et 3)
```

Le dossier de configuration est cherché dans cet ordre : variable d'environnement `TH_CONFIG_DIR`,
puis `config/` à la racine du dépôt (trouvée en remontant depuis le dossier courant).

## Dashboard

URL publique : <https://gasthorn.github.io/TradingHelper/> (**active après F10**, qui ajoute
le déploiement sur GitHub Pages).

En local :

```bash
cd dashboard
npm run dev                                         # serveur de développement
npm run build                                       # build statique dans dashboard/dist/
TH_DASHBOARD_BASE=/TradingHelper/ npm run build     # build avec le chemin de base de GitHub Pages
```

Les données affichées (`dashboard/public/data/`) sont générées par `th export` et ne sont jamais commitées.

### Réglages manuels du dépôt GitHub

À faire une fois dans les paramètres du dépôt (requis par les workflows de F10) :
- **Settings → Pages → Build and deployment → Source** : « GitHub Actions » ;
- **Settings → Actions → General → Workflow permissions** : « Read and write permissions ».

## Licence

[MIT](LICENSE).
