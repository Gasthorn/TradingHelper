"""Doublures de test pour l'ingestion (F01 — R16) : aucune ne fait d'appel réseau."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime

from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.source import RawBar, SourceError


def make_bars(cal: NyseCalendar, start: date, end: date, *, base: float = 100.0) -> list[RawBar]:
    """Barres synthétiques déterministes sur les séances NYSE de `[start, end]`.

    Valides après arrondi (low < open, close < high), avec `adj_close != close`.
    Le prix dépend de la date (et non du rang) : deux appels sur des plages qui se recouvrent
    donnent les mêmes barres aux mêmes dates.
    """
    bars: list[RawBar] = []
    for day in cal.sessions(start, end):
        p = base + (day.toordinal() % 1000) * 0.25
        bars.append(
            RawBar(
                date=day,
                open=p,
                high=p + 1.5,
                low=p - 1.5,
                close=p + 0.5,
                adj_close=round((p + 0.5) * 0.98, 4),
                volume=float(1_000_000 + day.toordinal() % 1000),
            )
        )
    return bars


class FakePriceSource:
    """`PriceSource` scriptable.

    - `data` : historique complet par symbole de config (filtré par dates à chaque appel) ;
    - `missing` : symboles toujours absents de la réponse ;
    - `fail_times` : nombre d'appels qui lèvent `ConnectionError` pour ce symbole ;
    - `always_fail` : symboles dont tout appel les contenant lève `ConnectionError` ;
    - `extra` : barres ajoutées telles quelles (sales, hors séance…), sans filtre de dates.

    Comme la vraie source, lève `SourceError` si aucun symbole demandé n'a de donnée.
    `calls` journalise chaque appel : `(symboles, start, end)`.
    """

    def __init__(
        self,
        data: Mapping[str, Sequence[RawBar]],
        *,
        missing: Iterable[str] = (),
        fail_times: Mapping[str, int] | None = None,
        always_fail: Iterable[str] = (),
        extra: Mapping[str, Sequence[RawBar]] | None = None,
    ) -> None:
        self.data: dict[str, list[RawBar]] = {s: list(b) for s, b in data.items()}
        self.missing = set(missing)
        self.fail_times = dict(fail_times or {})
        self.always_fail = set(always_fail)
        self.extra: dict[str, list[RawBar]] = {s: list(b) for s, b in (extra or {}).items()}
        self.calls: list[tuple[tuple[str, ...], date, date]] = []

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> Mapping[str, list[RawBar]]:
        self.calls.append((tuple(symbols), start, end))
        failing = sorted(s for s in symbols if s in self.always_fail)
        failing += sorted(s for s in symbols if self.fail_times.get(s, 0) > 0)
        if failing:
            for symbol in symbols:
                if self.fail_times.get(symbol, 0) > 0:
                    self.fail_times[symbol] -= 1
            raise ConnectionError(f"échec simulé pour {', '.join(failing)}")
        result: dict[str, list[RawBar]] = {}
        for symbol in symbols:
            if symbol in self.missing:
                continue
            bars = [b for b in self.data.get(symbol, []) if start <= b.date <= end]
            bars += self.extra.get(symbol, [])
            if bars:
                result[symbol] = bars
        if symbols and not result:
            raise SourceError(f"aucune donnée pour {', '.join(symbols)}")
        return result


class FakeClock:
    """Horloge injectable : `clock()` renvoie `clock.now` (modifiable entre deux runs)."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class RecordingSleep:
    """`sleep` injectable qui n'attend pas et journalise les délais demandés."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
