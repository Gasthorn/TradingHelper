"""Fonctions pures sur les barres (F01 R3 à R6) : nettoyage, fusion du recouvrement,
détection de révision. Aucune E/S ici (CLAUDE.md : fonctions pures isolées des effets de bord).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date

from tradinghelper.data.source import RawBar
from tradinghelper.schemas import PRICE_DECIMALS, Bar, IngestWarning, WarningRule


@dataclass(frozen=True)
class Cleaned:
    """Barres conformes au contrat §2 (triées par date) et barres écartées (R6)."""

    bars: list[Bar] = field(default_factory=list)
    warnings: list[IngestWarning] = field(default_factory=list)


def _validate(
    raw: RawBar, *, last_session: date, is_session: Callable[[date], bool]
) -> Bar | WarningRule:
    """Barre arrondie si elle est valide, sinon la première règle violée."""
    values = (raw.open, raw.high, raw.low, raw.close, raw.adj_close, raw.volume)
    if not all(math.isfinite(value) for value in values):
        return "nan"
    if raw.date > last_session:
        return "after_last_session"
    try:
        session = is_session(raw.date)
    except ValueError:  # date hors de la plage du calendrier
        session = False
    if not session:
        return "non_session_date"
    open_, high, low, close, adj_close = (
        round(price, PRICE_DECIMALS)
        for price in (raw.open, raw.high, raw.low, raw.close, raw.adj_close)
    )
    if min(open_, high, low, close, adj_close) <= 0:
        return "non_positive_price"
    if raw.volume < 0:
        return "negative_volume"
    # Après arrondi : c'est la barre écrite qui doit respecter le contrat.
    if low > min(open_, close) or high < max(open_, close):
        return "ohlc_inconsistent"
    return (raw.date, open_, high, low, close, adj_close, round(raw.volume))


def clean_bars(
    symbol: str,
    raw: Sequence[RawBar],
    *,
    last_session: date,
    is_session: Callable[[date], bool],
) -> Cleaned:
    """Arrondit (R5) et écarte les barres invalides avec un avertissement (R6).

    Une date en double garde sa dernière occurrence (avertissement `duplicate_date`), qui est
    ensuite validée comme les autres. Un volume nul est conservé (signalé par F02).
    """
    latest: dict[date, RawBar] = {}
    warnings: list[IngestWarning] = []
    for bar in raw:
        if bar.date in latest:
            warnings.append(IngestWarning(symbol=symbol, date=bar.date, rule="duplicate_date"))
        latest[bar.date] = bar

    kept: list[Bar] = []
    for bar in latest.values():
        outcome = _validate(bar, last_session=last_session, is_session=is_session)
        if isinstance(outcome, str):
            warnings.append(IngestWarning(symbol=symbol, date=bar.date, rule=outcome))
        else:
            kept.append(outcome)
    kept.sort(key=lambda b: b[0])
    return Cleaned(bars=kept, warnings=warnings)
