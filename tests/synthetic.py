"""Générateur de fichiers de prix synthétiques pour les tests de volume (F08 — R19).

Marche aléatoire géométrique seedée : aucun réseau, résultat identique pour un même
`numpy.random.Generator` (CLAUDE.md). Les fichiers respectent le contrat §2 et les règles
bloquantes de F02 ; les prix gardent 4 décimales (pire cas pour la taille des exports).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

from tradinghelper.data.storage import dumps_prices
from tradinghelper.schemas import PRICE_COLUMNS, Bar, PricesFile

LAST_UPDATED = datetime(2026, 11, 24, 22, 41, 5, tzinfo=UTC)


def synthetic_bars(sessions: Sequence[date], rng: np.random.Generator) -> list[Bar]:
    """Une barre par séance : clôtures en marche aléatoire, OHLC cohérents après arrondi."""
    n = len(sessions)
    if n == 0:
        return []
    start = rng.uniform(20.0, 500.0)
    close = start * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
    previous = np.concatenate(([start], close[:-1]))
    open_ = previous * np.exp(rng.normal(0.0, 0.005, n))
    high = np.maximum(open_, close) * (1.0 + np.abs(rng.normal(0.0, 0.008, n)))
    low = np.minimum(open_, close) * (1.0 - np.abs(rng.normal(0.0, 0.008, n)))
    adj_factor = np.linspace(rng.uniform(0.7, 0.95), 1.0, n)
    volume = rng.integers(1_000_000, 50_000_000, n)

    o, h, lo, c = (np.round(a, 4) for a in (open_, high, low, close))
    # L'arrondi peut casser low <= min(open, close) <= max(open, close) <= high : on borne.
    h = np.maximum(h, np.maximum(o, c))
    lo = np.minimum(lo, np.minimum(o, c))
    adj = np.round(c * adj_factor, 4)

    return [
        (day, float(o[i]), float(h[i]), float(lo[i]), float(c[i]), float(adj[i]), int(volume[i]))
        for i, day in enumerate(sessions)
    ]


def write_synthetic_prices(
    directory: Path, symbols: Sequence[str], sessions: Sequence[date], rng: np.random.Generator
) -> dict[str, Path]:
    """Écrit `{directory}/{SYMBOL}.json` (sérialisation canonique) pour chaque symbole, dans
    l'ordre donné, avec le même générateur : même seed → mêmes octets."""
    directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for symbol in symbols:
        prices = PricesFile(
            schema_version=1,
            symbol=symbol,
            currency="USD",
            source="yfinance",
            columns=PRICE_COLUMNS,
            last_updated=LAST_UPDATED,
            bars=synthetic_bars(sessions, rng),
        )
        path = directory / f"{symbol}.json"
        path.write_text(dumps_prices(prices), encoding="utf-8", newline="\n")
        paths[symbol] = path
    return paths
