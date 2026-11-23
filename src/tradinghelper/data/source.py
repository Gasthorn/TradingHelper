"""Source des cours : interface `PriceSource` et adaptateur yfinance (F01 R5, R10 à R12, R16).

Seul module qui importe `yfinance` et `pandas` (effets de bord réseau isolés ici) : il renvoie
des `RawBar` Python purs, la logique métier ne voit jamais de DataFrame.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final, Protocol

import pandas as pd
import yfinance as yf

# Colonnes renvoyées par `yf.download(auto_adjust=False)`, dans l'ordre de `RawBar`.
_YF_FIELDS: Final = ("Open", "High", "Low", "Close", "Adj Close", "Volume")


@dataclass(frozen=True, slots=True)
class RawBar:
    """Barre brute telle que fournie par la source : non arrondie, valeurs NaN possibles.

    `open`/`high`/`low`/`close` sont ajustés des splits seulement ; `adj_close` des splits et
    des dividendes (R5). Le nettoyage (R6) est fait par `data.bars.clean_bars`.
    """

    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: float


class SourceError(Exception):
    """Échec d'un appel à la source sans exception de la bibliothèque (ex. aucune donnée)."""


class PriceSource(Protocol):
    def fetch(self, symbols: Sequence[str], start: date, end: date) -> Mapping[str, list[RawBar]]:
        """Barres journalières de `start` à `end` (bornes incluses) pour des symboles de config.

        Le résultat est indexé par symbole de config. Un symbole sans donnée est omis ; si
        **aucun** symbole demandé n'a de donnée, l'appel échoue (`SourceError`). Toute erreur
        réseau ou limitation de débit lève une exception : l'appelant applique les relances.
        """
        ...


def to_provider_symbol(symbol: str) -> str:
    """Symbole de config -> symbole yfinance : `BRK.B` -> `BRK-B` (R12)."""
    return symbol.replace(".", "-")


def _session_date(stamp: Any) -> date:
    # Index journalier yfinance : sans fuseau (`ignore_tz`) ou à l'heure de la place ;
    # dans les deux cas, la date locale est la date de séance.
    return date(stamp.year, stamp.month, stamp.day)


def _to_raw_bars(frame: Any) -> list[RawBar]:
    """Sous-DataFrame d'un ticker (colonnes `_YF_FIELDS`) -> barres, lignes entièrement NaN
    exclues (dates propres aux autres tickers du lot)."""
    bars: list[RawBar] = []
    for stamp, row in frame.iterrows():
        values = [float(row[field]) for field in _YF_FIELDS]
        if all(math.isnan(value) for value in values):
            continue
        bars.append(RawBar(_session_date(stamp), *values))
    return bars


class YFinanceSource:
    """Adaptateur `yf.download` (multi-tickers, journalier, non ajusté)."""

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> Mapping[str, list[RawBar]]:
        if not symbols:
            return {}
        provider = {to_provider_symbol(symbol): symbol for symbol in symbols}
        frame = yf.download(
            list(provider),
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),  # borne de fin exclue chez yfinance
            interval="1d",
            auto_adjust=False,
            actions=False,
            progress=False,
            group_by="ticker",
            multi_level_index=True,
        )
        result: dict[str, list[RawBar]] = {}
        if isinstance(frame, pd.DataFrame) and isinstance(frame.columns, pd.MultiIndex):
            available = set(frame.columns.get_level_values(0))
            for ticker, symbol in provider.items():
                if ticker in available:
                    bars = _to_raw_bars(frame[ticker])
                    if bars:
                        result[symbol] = bars
        if not result:
            # yf.download avale les erreurs (réseau, limitation de débit, symbole inconnu) et
            # renvoie des colonnes vides : sans aucune donnée, l'appel est un échec (R10).
            raise SourceError(f"aucune donnée renvoyée par yfinance pour {', '.join(symbols)}")
        return result
