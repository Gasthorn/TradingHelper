"""Tests des fonctions pures sur les barres (F01 — R5, R6 ; R3, R4 en T11)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from tradinghelper.data.bars import clean_bars
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.source import RawBar
from tradinghelper.schemas import PRICE_COLUMNS, PricesFile

CAL = NyseCalendar()
S = date(2026, 11, 24)  # dernière séance clôturée des tests

NAN = float("nan")


def _raw(day: date, **changes: float) -> RawBar:
    values: dict[str, Any] = {
        "open": 228.1,
        "high": 231.45,
        "low": 227.8,
        "close": 230.95,
        "adj_close": 229.7312,
        "volume": 51234000.0,
    }
    values.update(changes)
    return RawBar(date=day, **values)


def _clean(raw: list[RawBar], last_session: date = S) -> Any:
    return clean_bars("AAPL", raw, last_session=last_session, is_session=CAL.is_session)


def _assert_valid_contract(bars: list[Any]) -> None:
    PricesFile.model_validate(
        {
            "schema_version": 1,
            "symbol": "AAPL",
            "currency": "USD",
            "source": "yfinance",
            "columns": list(PRICE_COLUMNS),
            "last_updated": "2026-11-24T22:00:00Z",
            "bars": bars,
        }
    )


def test_valid_bar_kept_without_warning() -> None:
    cleaned = _clean([_raw(date(2026, 11, 23))])

    assert cleaned.bars == [(date(2026, 11, 23), 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000)]
    assert cleaned.warnings == []


def test_prices_rounded_to_4_decimals_volume_int() -> None:
    raw = _raw(
        date(2026, 11, 23),
        open=228.123449,
        high=231.45006,
        low=227.79996,
        close=230.950049,
        adj_close=229.73124999,
        volume=51234000.0,
    )

    (bar,) = _clean([raw]).bars

    assert bar == (date(2026, 11, 23), 228.1234, 231.4501, 227.8, 230.95, 229.7312, 51234000)
    assert type(bar[6]) is int
    _assert_valid_contract([bar])


DROP_CASES: dict[str, tuple[RawBar, str]] = {
    "nan": (_raw(date(2026, 11, 23), high=NAN), "nan"),
    "volume_nan": (_raw(date(2026, 11, 23), volume=NAN), "nan"),
    "infini": (_raw(date(2026, 11, 23), close=float("inf")), "nan"),
    "weekend": (_raw(date(2026, 11, 22)), "non_session_date"),
    "holiday": (_raw(date(2026, 9, 7)), "non_session_date"),  # Labor Day
    "after_S": (_raw(date(2026, 11, 25)), "after_last_session"),
    "non_positive": (_raw(date(2026, 11, 23), adj_close=0.0), "non_positive_price"),
    "rounds_to_zero": (_raw(date(2026, 11, 23), adj_close=0.00004), "non_positive_price"),
    "negative_price": (_raw(date(2026, 11, 23), open=-1.0, low=-2.0), "non_positive_price"),
    "negative_volume": (_raw(date(2026, 11, 23), volume=-5.0), "negative_volume"),
    "high_lt_low": (_raw(date(2026, 11, 23), high=200.0), "ohlc_inconsistent"),
    "low_gt_close": (_raw(date(2026, 11, 23), low=231.0), "ohlc_inconsistent"),
    # Incohérence révélée par l'arrondi : low 228.10004 -> 228.1 = open (accepté) ;
    # high 230.94996 -> 230.95 = close (accepté) ; low 228.10006 -> 228.1001 > open (refusé).
    "high_lt_low_after_rounding": (_raw(date(2026, 11, 23), low=228.10006), "ohlc_inconsistent"),
}


@pytest.mark.parametrize(("raw", "rule"), list(DROP_CASES.values()), ids=list(DROP_CASES))
def test_drops_invalid_bars(raw: RawBar, rule: str) -> None:
    good = _raw(date(2026, 11, 20))

    cleaned = _clean([good, raw])

    assert [bar[0] for bar in cleaned.bars] == [date(2026, 11, 20)]
    assert len(cleaned.warnings) == 1
    warning = cleaned.warnings[0]
    assert (warning.symbol, warning.date, warning.rule) == ("AAPL", raw.date, rule)


def test_rounding_can_make_bar_valid() -> None:
    raw = _raw(date(2026, 11, 23), low=228.10004, high=230.94996)

    (bar,) = _clean([raw]).bars

    assert bar[3] == 228.1
    assert bar[2] == 230.95


def test_dedup_keeps_last_occurrence() -> None:
    first = _raw(date(2026, 11, 23), volume=1.0)
    last = _raw(date(2026, 11, 23), volume=2.0)

    cleaned = _clean([first, _raw(date(2026, 11, 20)), last])

    assert [(bar[0], bar[6]) for bar in cleaned.bars] == [
        (date(2026, 11, 20), 51234000),
        (date(2026, 11, 23), 2),
    ]
    assert [(w.date, w.rule) for w in cleaned.warnings] == [(date(2026, 11, 23), "duplicate_date")]


def test_zero_volume_kept() -> None:
    cleaned = _clean([_raw(date(2026, 11, 23), volume=0.0)])

    assert cleaned.bars[0][6] == 0
    assert cleaned.warnings == []


def test_output_sorted_by_date() -> None:
    days = [date(2026, 11, 24), date(2026, 11, 18), date(2026, 11, 20)]

    cleaned = _clean([_raw(day) for day in days])

    assert [bar[0] for bar in cleaned.bars] == sorted(days)


def test_empty_input() -> None:
    cleaned = _clean([])

    assert cleaned.bars == []
    assert cleaned.warnings == []


def test_warnings_in_input_order() -> None:
    cleaned = _clean([_raw(date(2026, 11, 22)), _raw(date(2026, 11, 21), close=NAN)])

    assert [(w.date, w.rule) for w in cleaned.warnings] == [
        (date(2026, 11, 22), "non_session_date"),
        (date(2026, 11, 21), "nan"),
    ]


def test_output_always_satisfies_contract() -> None:
    raw = [_raw(day) for day in CAL.sessions(date(2026, 10, 1), S)]
    raw += [_raw(date(2026, 11, 22)), _raw(date(2026, 11, 25)), _raw(S, high=1.0)]

    cleaned = _clean(raw)

    _assert_valid_contract(cleaned.bars)
    # La barre invalide datée de S remplace (dédoublonnage) la barre valide du même jour.
    assert sorted(w.rule for w in cleaned.warnings) == [
        "after_last_session",
        "duplicate_date",
        "non_session_date",
        "ohlc_inconsistent",
    ]
    assert cleaned.bars[-1][0] == CAL.shift(S, -1)
