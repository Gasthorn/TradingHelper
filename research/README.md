# research/

Explorations libres : notebooks, scripts jetables, prototypes de features ou de modèles.

Règles (constitution P9, spec F00 R5) :
- Rien dans `src/` n'importe ce dossier ; le pipeline ne dépend jamais d'une exploration.
- Ce dossier n'est pas soumis à `ruff` ni à `mypy`.
- Une idée validée est réécrite proprement dans `src/`, avec spec et tests, en suivant le workflow SDD.
- Ne pas y commiter de données volumineuses ni de modèles > 2 Mo.
