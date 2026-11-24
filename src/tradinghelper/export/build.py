"""Construction pure des fichiers d'export du dashboard (F08, contrat §7).

Aucune E/S ici : les données sont reçues déjà chargées et les fichiers sont rendus en octets,
écrits ensuite par `export/dashboard.py`. Chaque fichier passe par son modèle pydantic (R1).
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Final

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel

# Grille d'arrondi (spec F08, Définitions ; R14).
PRICE_DECIMALS: Final = 4  # prix et indicateurs de prix (cours anciens ajustés < 1 $)
RSI_DECIMALS: Final = 2
RATIO_DECIMALS: Final = 4  # ratios, rendements, poids, confiances, métriques
MONEY_DECIMALS: Final = 2  # equity, cash (M3)

#: Longueur des empreintes du manifest (préfixe du SHA-256 hexadécimal, R11).
DIGEST_LENGTH: Final = 16


def rounded(values: npt.NDArray[np.float64], decimals: int) -> list[float | None]:
    """Valeurs arrondies à `decimals` décimales, en flottants Python ; `NaN` → `None`
    (warm-up, R8). Un infini est une erreur de calcul : `ValueError`."""
    if np.isinf(values).any():
        raise ValueError("valeur infinie dans une série à exporter")
    result: list[float | None] = []
    for value in np.round(values, decimals).tolist():
        result.append(None if math.isnan(value) else value)
    return result


def render(model: BaseModel) -> bytes:
    """JSON minifié UTF-8 du modèle (R14) : séparateurs sans espace, accents non échappés,
    clés JSON (alias), et `allow_nan=False` comme seconde barrière contre `NaN` (R8)."""
    payload = model.model_dump(mode="json", by_alias=True)
    try:
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except ValueError as exc:
        raise ValueError(f"valeur non représentable en JSON ({exc})") from exc
    return text.encode("utf-8")


def digest(content: bytes) -> str:
    """Empreinte d'un fichier pour le manifest : 16 premiers caractères hex du SHA-256 (R11)."""
    return hashlib.sha256(content).hexdigest()[:DIGEST_LENGTH]
