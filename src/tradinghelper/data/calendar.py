"""Calendrier NYSE : séances, horaires de clôture (demi-séances comprises), dernière séance
clôturée `S` (F01 R7, R3).

Seul module qui importe `pandas_market_calendars` (non typé) : tout ce qui en sort est converti
en `datetime.date` / `datetime.datetime` natifs. Le calendrier est calculé hors ligne, une fois
par plage et par processus, à la première utilisation.
"""

from __future__ import annotations

import bisect
from datetime import UTC, date, datetime, timedelta
from functools import cache
from typing import Final

import pandas_market_calendars as mcal

# Délai après la clôture avant de considérer une séance comme close (marge yfinance, F01 R7).
CLOSE_MARGIN: Final = timedelta(minutes=30)

DEFAULT_FIRST: Final = date(1990, 1, 1)
DEFAULT_LAST: Final = date(2040, 12, 31)


@cache
def _build_schedule(first: date, last: date) -> tuple[list[date], dict[date, datetime]]:
    """Séances et clôtures UTC de `[first, last]`, calculées une fois par plage (~0,3 s)."""
    frame = mcal.get_calendar("NYSE").schedule(
        start_date=first.isoformat(), end_date=last.isoformat()
    )
    sessions: list[date] = []
    closes: dict[date, datetime] = {}
    for stamp, close in zip(frame.index, frame["market_close"], strict=True):
        day: date = stamp.date()
        sessions.append(day)
        closes[day] = close.to_pydatetime().astimezone(UTC)
    return sessions, closes


class NyseCalendar:
    """Calendrier des séances NYSE sur une plage fixe `[first, last]` (déterministe)."""

    def __init__(self, first: date = DEFAULT_FIRST, last: date = DEFAULT_LAST) -> None:
        self._first = first
        self._last = last

    @property
    def _schedule(self) -> tuple[list[date], dict[date, datetime]]:
        return _build_schedule(self._first, self._last)

    @property
    def _sessions(self) -> list[date]:
        return self._schedule[0]

    def _check_range(self, *days: date) -> None:
        for day in days:
            if not self._first <= day <= self._last:
                raise ValueError(
                    f"{day.isoformat()} hors de la plage du calendrier "
                    f"[{self._first.isoformat()}, {self._last.isoformat()}]"
                )

    def sessions(self, start: date, end: date) -> list[date]:
        """Séances de `start` à `end`, bornes incluses (liste vide si `start > end`)."""
        if start > end:
            return []
        self._check_range(start, end)
        lo = bisect.bisect_left(self._sessions, start)
        hi = bisect.bisect_right(self._sessions, end)
        return self._sessions[lo:hi]

    def is_session(self, day: date) -> bool:
        self._check_range(day)
        return day in self._schedule[1]

    def _index_of(self, session: date) -> int:
        self._check_range(session)
        index = bisect.bisect_left(self._sessions, session)
        if index == len(self._sessions) or self._sessions[index] != session:
            raise ValueError(f"{session.isoformat()} n'est pas une séance NYSE")
        return index

    def shift(self, session: date, n: int) -> date:
        """Séance située `n` séances après `session` (`n < 0` : avant)."""
        target = self._index_of(session) + n
        if not 0 <= target < len(self._sessions):
            raise ValueError(
                f"décalage de {n} séances depuis {session.isoformat()} "
                "hors de la plage du calendrier"
            )
        return self._sessions[target]

    def market_close(self, session: date) -> datetime:
        """Heure de clôture de `session` en UTC (demi-séances comprises)."""
        return self._schedule[1][self._sessions[self._index_of(session)]]

    def last_closed_session(self, now: datetime) -> date:
        """`S` : dernière séance `d` telle que `now >= market_close(d) + CLOSE_MARGIN`."""
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("`now` doit porter un fuseau horaire")
        now_utc = now.astimezone(UTC)
        self._check_range(now_utc.date())
        # La clôture d'une séance tombe toujours le même jour en UTC (au plus 21:00 UTC).
        index = bisect.bisect_right(self._sessions, now_utc.date()) - 1
        while index >= 0:
            session = self._sessions[index]
            if now_utc >= self._schedule[1][session] + CLOSE_MARGIN:
                return session
            index -= 1
        raise ValueError(f"aucune séance clôturée avant {now_utc.isoformat()} dans le calendrier")
