"""Construction pure des fichiers d'export du dashboard (F08, contrat §7).

Aucune E/S ici : les données sont reçues déjà chargées et les fichiers sont rendus en octets,
écrits ensuite par `export/dashboard.py`. Chaque fichier passe par son modèle pydantic (R1).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from collections.abc import Set as AbstractSet
from typing import Final

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel

from tradinghelper.features.indicators import bollinger, rsi_wilder, sma
from tradinghelper.schemas import ExportMarker, PricesFile, SignalsFile, TickerFile, TickerSeries

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


# --- Fiche ticker (R6, R8, R9) -----------------------------------------------------------------


def build_ticker(prices: PricesFile, markers: Sequence[ExportMarker]) -> TickerFile:
    """`tickers/{SYMBOL}.json` : colonnes OHLCV recopiées des barres (déjà arrondies par F01),
    indicateurs calculés sur `close` et arrondis selon la grille (R14)."""
    bars = prices.bars
    close = np.array([bar[4] for bar in bars], dtype=np.float64)
    _middle, bb_upper, bb_lower = bollinger(close, n=20, k=2.0)
    series = TickerSeries(
        date=[bar[0] for bar in bars],
        open=[bar[1] for bar in bars],
        high=[bar[2] for bar in bars],
        low=[bar[3] for bar in bars],
        close=[bar[4] for bar in bars],
        volume=[bar[6] for bar in bars],
        sma20=rounded(sma(close, 20), PRICE_DECIMALS),
        sma50=rounded(sma(close, 50), PRICE_DECIMALS),
        sma200=rounded(sma(close, 200), PRICE_DECIMALS),
        bb_upper=rounded(bb_upper, PRICE_DECIMALS),
        bb_lower=rounded(bb_lower, PRICE_DECIMALS),
        rsi14=rounded(rsi_wilder(close, 14), RSI_DECIMALS),
    )
    return TickerFile(schema_version=1, symbol=prices.symbol, series=series, markers=list(markers))


def collect_markers(
    signals: Iterable[SignalsFile], symbols: AbstractSet[str]
) -> dict[str, list[ExportMarker]]:
    """Marqueurs BUY/SELL par symbole exporté (R9), datés par le fichier de signaux, triés par
    date puis `strategy_id`. Les HOLD et les symboles non exportés sont ignorés."""
    markers: dict[str, list[ExportMarker]] = {symbol: [] for symbol in sorted(symbols)}
    for file in signals:
        for signal in file.signals:
            if signal.symbol not in markers or signal.action == "HOLD":
                continue
            markers[signal.symbol].append(
                ExportMarker(
                    date=file.date,
                    strategy_id=signal.strategy_id,
                    action=signal.action,
                    confidence=round(signal.confidence, RATIO_DECIMALS),
                )
            )
    for found in markers.values():
        found.sort(key=lambda marker: (marker.date, marker.strategy_id))
    return markers
