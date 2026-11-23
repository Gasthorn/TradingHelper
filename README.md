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

Les étapes suivantes (`th ingest`, `th validate`, `th export`…) arrivent avec les features F01 et au-delà.

### Configuration

Toute commande charge et valide `config/universe.yaml`, `config/backtest.yaml` et `config/strategies.yaml`.
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
