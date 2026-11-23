"""Tests des fonctions pures sur les barres (F01 — R5, R6, R3, R4)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from tradinghelper.data.bars import (
    OVERLAP_SESSIONS,
    REVISION_TOL,
    clean_bars,
    merge_overlap,
    needs_rewrite,
)
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.source import RawBar
from tradinghelper.schemas import PRICE_COLUMNS, Bar, PricesFile

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


# --- Fusion du recouvrement (R3) et détection de révision (R4) ----------------------------------


def _bar(day: date, close: float = 230.95, adj: float = 229.7312, volume: int = 1000) -> Bar:
    return (day, 228.1, 240.0, 220.0, close, adj, volume)


D16, D17, D18, D19, D20, D23, D24 = (date(2026, 11, d) for d in (16, 17, 18, 19, 20, 23, 24))
STORED = [_bar(D16), _bar(D17), _bar(D18), _bar(D19), _bar(D20)]
SINCE = D17  # début de la fenêtre de recouvrement de la fixture : du 17 au 20/11


def test_constants() -> None:
    assert OVERLAP_SESSIONS == 5
    assert REVISION_TOL == 1e-4


def test_merge_appends_new_bars() -> None:
    fresh = [_bar(D17), _bar(D18), _bar(D19), _bar(D20), _bar(D23), _bar(D24)]

    merge = merge_overlap("AAPL", STORED, fresh, since=SINCE)

    assert merge.bars == [*STORED, _bar(D23), _bar(D24)]
    assert (merge.added, merge.revised, merge.warnings) == (2, 0, [])


def test_merge_identical_overlap_counts_nothing() -> None:
    merge = merge_overlap("AAPL", STORED, STORED[1:], since=SINCE)

    assert merge.bars == STORED
    assert (merge.added, merge.revised, merge.warnings) == (0, 0, [])


def test_merge_replaces_revised_volume_bar() -> None:
    fresh = [_bar(D17), _bar(D18), _bar(D19), _bar(D20, volume=2000), _bar(D23)]

    merge = merge_overlap("AAPL", STORED, fresh, since=SINCE)

    assert merge.bars[4] == _bar(D20, volume=2000)
    assert merge.bars[-1] == _bar(D23)
    assert (merge.added, merge.revised) == (1, 1)


def test_merge_keeps_stored_bar_missing_from_response() -> None:
    fresh = [_bar(D17), _bar(D19), _bar(D20), _bar(D23)]

    merge = merge_overlap("AAPL", STORED, fresh, since=SINCE)

    assert merge.bars == [*STORED, _bar(D23)]
    assert [(w.symbol, w.date, w.rule) for w in merge.warnings] == [
        ("AAPL", D18, "missing_overlap_bar")
    ]


def test_merge_ignores_fresh_bars_before_since() -> None:
    fresh = [_bar(D16, volume=9), _bar(D17), _bar(D23)]

    merge = merge_overlap("AAPL", STORED, fresh, since=SINCE)

    assert merge.bars[0] == _bar(D16)
    assert merge.added == 1


def test_merge_fills_gap_inside_overlap() -> None:
    stored = [_bar(D16), _bar(D17), _bar(D19), _bar(D20)]
    fresh = [_bar(D17), _bar(D18), _bar(D19), _bar(D20)]

    merge = merge_overlap("AAPL", stored, fresh, since=SINCE)

    assert [b[0] for b in merge.bars] == [D16, D17, D18, D19, D20]
    assert merge.added == 1


def test_merge_output_sorted_and_unique() -> None:
    fresh = [_bar(D24), _bar(D17), _bar(D23)]

    merge = merge_overlap("AAPL", STORED, fresh, since=SINCE)

    dates = [b[0] for b in merge.bars]
    assert dates == sorted(set(dates))


def test_merge_does_not_mutate_inputs() -> None:
    stored = list(STORED)
    fresh = [_bar(D20, volume=5), _bar(D23)]

    merge_overlap("AAPL", stored, fresh, since=SINCE)

    assert stored == STORED


def test_needs_rewrite_on_dividend_adj_close_change() -> None:
    # Dividende de 0,3 % : yfinance réajuste tout l'historique d'adj_close.
    fresh = [_bar(d, adj=round(229.7312 * 0.997, 4)) for d in (D17, D18, D19, D20)]

    assert needs_rewrite(STORED, fresh, since=SINCE) is True


def test_needs_rewrite_on_split_close_change() -> None:
    # Split 2:1 : OHLC (ajustés des splits) divisés par 2.
    fresh = [_bar(D20, close=230.95 / 2, adj=229.7312 / 2)]

    assert needs_rewrite(STORED, fresh, since=SINCE) is True


def test_needs_rewrite_on_close_only() -> None:
    assert needs_rewrite(STORED, [_bar(D19, close=231.5)], since=SINCE) is True


@pytest.mark.parametrize("factor", [1 + 0.9e-4, 1 - 0.9e-4, 1.0])
def test_no_rewrite_within_tolerance(factor: float) -> None:
    fresh = [_bar(D20, close=230.95 * factor, adj=229.7312 * factor)]

    assert needs_rewrite(STORED, fresh, since=SINCE) is False


def test_just_above_tolerance_triggers_rewrite() -> None:
    fresh = [_bar(D20, adj=229.7312 * (1 + 1.1e-4))]

    assert needs_rewrite(STORED, fresh, since=SINCE) is True


def test_volume_or_ohlc_change_is_not_a_rewrite() -> None:
    fresh = [(D20, 228.5, 241.0, 219.0, 230.95, 229.7312, 99999)]

    assert needs_rewrite(STORED, fresh, since=SINCE) is False


def test_needs_rewrite_ignores_bars_before_since() -> None:
    fresh = [_bar(D16, adj=1.0), _bar(D17)]

    assert needs_rewrite(STORED, fresh, since=SINCE) is False


def test_needs_rewrite_ignores_new_bars() -> None:
    assert needs_rewrite(STORED, [_bar(D23, close=999.0, adj=999.0)], since=SINCE) is False
