"""Fonctions pures sur les barres (F01 R3 à R6) : nettoyage, fusion du recouvrement,
détection de révision. Aucune E/S ici (CLAUDE.md : fonctions pures isolées des effets de bord).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final

from tradinghelper.data.source import RawBar
from tradinghelper.schemas import PRICE_DECIMALS, Bar, IngestWarning, WarningRule

# Séances re-téléchargées avant la dernière barre stockée pour détecter les révisions (R3).
OVERLAP_SESSIONS: Final = 5

# Écart relatif sur `close` ou `adj_close` au-delà duquel l'historique est réécrit (R4).
# Les prix étant arrondis à 4 décimales, le bruit d'arrondi reste sous ce seuil pour tout
# prix >= 1 $ (vrai pour l'univers v1 de grandes capitalisations).
REVISION_TOL: Final = 1e-4


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


@dataclass(frozen=True)
class Merge:
    """Résultat de la fusion du recouvrement (R3)."""

    bars: list[Bar]
    added: int
    revised: int
    warnings: list[IngestWarning] = field(default_factory=list)


def _relative_change(old: float, new: float) -> float:
    return abs(new - old) / abs(old)


def needs_rewrite(stored: Sequence[Bar], fresh: Sequence[Bar], *, since: date) -> bool:
    """Vrai si, sur une séance `>= since` présente des deux côtés, `close` ou `adj_close`
    diffère de plus de `REVISION_TOL` (split, dividende : historique ajusté réécrit, R4)."""
    by_date = {bar[0]: bar for bar in stored if bar[0] >= since}
    for bar in fresh:
        old = by_date.get(bar[0])
        if old is None:
            continue
        if (
            _relative_change(old[4], bar[4]) > REVISION_TOL
            or _relative_change(old[5], bar[5]) > REVISION_TOL
        ):
            return True
    return False


def merge_overlap(
    symbol: str, stored: Sequence[Bar], fresh: Sequence[Bar], *, since: date
) -> Merge:
    """Fusionne une réponse incrémentale dans l'historique stocké (R3).

    - barre fraîche datée `>= since` absente du stock (nouvelle séance ou trou) : ajoutée ;
    - barre du recouvrement différente : remplacée (`revised`) ;
    - barre stockée du recouvrement absente de la réponse : conservée, avertissement ;
    - barres stockées antérieures à `since` : intactes (les barres fraîches plus anciennes
      sont ignorées).
    """
    merged = {bar[0]: bar for bar in stored}
    fresh_dates: set[date] = set()
    added = revised = 0
    for bar in fresh:
        day = bar[0]
        if day < since:
            continue
        fresh_dates.add(day)
        old = merged.get(day)
        if old is None:
            added += 1
        elif old != bar:
            revised += 1
        merged[day] = bar
    warnings = [
        IngestWarning(symbol=symbol, date=bar[0], rule="missing_overlap_bar")
        for bar in stored
        if bar[0] >= since and bar[0] not in fresh_dates
    ]
    return Merge(
        bars=[merged[day] for day in sorted(merged)],
        added=added,
        revised=revised,
        warnings=warnings,
    )
