"""Tests du calendrier NYSE (F01 — R7, R3). Le calendrier est calculé hors ligne.

Heures exprimées en UTC : en novembre, ET = UTC-5 (clôture normale 16 h ET = 21:00 UTC,
demi-séance 13 h ET = 18:00 UTC) ; en juillet, ET = UTC-4.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from tradinghelper.data.calendar import CLOSE_MARGIN, NyseCalendar


@pytest.fixture(scope="module")
def cal() -> NyseCalendar:
    return NyseCalendar()


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_close_margin_is_30_minutes() -> None:
    assert timedelta(minutes=30) == CLOSE_MARGIN


def test_sessions_exclude_weekends_and_holidays(cal: NyseCalendar) -> None:
    # 26/11/2026 : Thanksgiving ; 28-29 : week-end.
    assert cal.sessions(date(2026, 11, 23), date(2026, 11, 30)) == [
        date(2026, 11, 23),
        date(2026, 11, 24),
        date(2026, 11, 25),
        date(2026, 11, 27),
        date(2026, 11, 30),
    ]


def test_sessions_bounds_inclusive_and_empty_range(cal: NyseCalendar) -> None:
    assert cal.sessions(date(2026, 11, 27), date(2026, 11, 27)) == [date(2026, 11, 27)]
    assert cal.sessions(date(2026, 11, 28), date(2026, 11, 29)) == []
    assert cal.sessions(date(2026, 11, 30), date(2026, 11, 23)) == []


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 11, 25), True),
        (date(2026, 11, 26), False),  # Thanksgiving
        (date(2026, 11, 27), True),  # demi-séance
        (date(2026, 11, 28), False),  # samedi
        (date(2026, 12, 25), False),  # Noël
        (date(2026, 7, 3), False),  # 4 juillet tombant un samedi : férié le vendredi
    ],
)
def test_is_session(cal: NyseCalendar, day: date, expected: bool) -> None:
    assert cal.is_session(day) is expected


def test_shift_back_5_sessions_skips_holidays(cal: NyseCalendar) -> None:
    # 30/11 - 5 séances : 27, 25, 24, 23, 20 (le 26 est férié).
    assert cal.shift(date(2026, 11, 30), -5) == date(2026, 11, 20)


def test_shift_forward_and_zero(cal: NyseCalendar) -> None:
    assert cal.shift(date(2026, 11, 25), 1) == date(2026, 11, 27)
    assert cal.shift(date(2026, 11, 25), 0) == date(2026, 11, 25)


def test_shift_requires_a_session(cal: NyseCalendar) -> None:
    with pytest.raises(ValueError, match="2026-11-26"):
        cal.shift(date(2026, 11, 26), -5)


def test_market_close_normal_day_winter(cal: NyseCalendar) -> None:
    assert cal.market_close(date(2026, 11, 24)) == _utc(2026, 11, 24, 21, 0)


def test_market_close_normal_day_summer(cal: NyseCalendar) -> None:
    assert cal.market_close(date(2026, 7, 6)) == _utc(2026, 7, 6, 20, 0)


def test_market_close_half_day_2026_11_27(cal: NyseCalendar) -> None:
    close = cal.market_close(date(2026, 11, 27))

    assert close == _utc(2026, 11, 27, 18, 0)
    assert type(close) is datetime  # pas de pandas.Timestamp hors du wrapper


def test_market_close_requires_a_session(cal: NyseCalendar) -> None:
    with pytest.raises(ValueError, match="2026-11-28"):
        cal.market_close(date(2026, 11, 28))


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # 15 h ET un jour de séance : la séance du jour n'est pas clôturée.
        (_utc(2026, 11, 24, 20, 0), date(2026, 11, 23)),
        # Clôture + 29 min : marge non atteinte.
        (_utc(2026, 11, 24, 21, 29), date(2026, 11, 23)),
        # Clôture + 30 min : séance du jour clôturée.
        (_utc(2026, 11, 24, 21, 30), date(2026, 11, 24)),
        # Cron quotidien 22:30 UTC.
        (_utc(2026, 11, 24, 22, 30), date(2026, 11, 24)),
        # Demi-séance : 13 h 45 ET (clôture 13 h + 45 min).
        (_utc(2026, 11, 27, 18, 45), date(2026, 11, 27)),
        # Demi-séance : 13 h 20 ET, marge non atteinte.
        (_utc(2026, 11, 27, 18, 20), date(2026, 11, 25)),
        # Jour férié (Thanksgiving) en soirée.
        (_utc(2026, 11, 26, 23, 0), date(2026, 11, 25)),
        # Samedi.
        (_utc(2026, 11, 28, 12, 0), date(2026, 11, 27)),
        # Cron retardé après minuit UTC : toujours la séance de la veille.
        (_utc(2026, 11, 25, 0, 30), date(2026, 11, 24)),
        # Lundi matin avant l'ouverture : vendredi.
        (_utc(2026, 11, 30, 13, 0), date(2026, 11, 27)),
    ],
)
def test_last_closed_session(cal: NyseCalendar, now: datetime, expected: date) -> None:
    assert cal.last_closed_session(now) == expected


def test_last_closed_session_accepts_any_timezone(cal: NyseCalendar) -> None:
    from datetime import timezone

    eastern_winter = timezone(timedelta(hours=-5))

    assert cal.last_closed_session(datetime(2026, 11, 24, 16, 30, tzinfo=eastern_winter)) == date(
        2026, 11, 24
    )


def test_last_closed_session_rejects_naive_datetime(cal: NyseCalendar) -> None:
    with pytest.raises(ValueError, match="fuseau"):
        cal.last_closed_session(datetime(2026, 11, 24, 22, 30))


def test_out_of_range_raises(cal: NyseCalendar) -> None:
    with pytest.raises(ValueError, match="hors de la plage"):
        cal.last_closed_session(_utc(2100, 1, 4, 22, 0))
    with pytest.raises(ValueError, match="hors de la plage"):
        cal.sessions(date(1980, 1, 1), date(1980, 2, 1))
