"""Tests des règles pures de qualité des données (F02 — R2, R3)."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import pytest

from tradinghelper.data import bars, quality
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.quality import (
    LARGE_MOVE_LOG,
    RowCheck,
    check_rows,
    large_moves,
    zero_volumes,
)
from tradinghelper.schemas import Bar

CAL = NyseCalendar()
S = date(2026, 11, 24)  # dernière séance clôturée des tests (mardi)

# Lignes valides : vendredi 20, lundi 23 et mardi 24 novembre 2026.
VALID_ROWS: list[list[Any]] = [
    ["2026-11-20", 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000],
    ["2026-11-23", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000],
    ["2026-11-24", 232.4, 234.0, 231.0, 233.5, 232.2671, 45000000],
]


def _rows(index: int | None = None, row: list[Any] | None = None) -> list[Any]:
    """Copie de `VALID_ROWS`, la ligne `index` remplacée par `row`."""
    rows: list[Any] = [list(r) for r in VALID_ROWS]
    if index is not None:
        rows[index] = row
    return rows


def _check(rows: list[Any], symbol: str = "AAPL") -> RowCheck:
    return check_rows(symbol, rows, last_session=S, is_session=CAL.is_session)


def _rules(result: RowCheck) -> list[tuple[date | None, str]]:
    return [(v.date, v.rule) for v in result.violations]


# --- Lignes valides ----------------------------------------------------------------------------


def test_valid_rows_return_bars() -> None:
    result = _check(_rows())

    assert result.violations == []
    assert result.bars == [
        (date(2026, 11, 20), 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000),
        (date(2026, 11, 23), 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000),
        (date(2026, 11, 24), 232.4, 234.0, 231.0, 233.5, 232.2671, 45000000),
    ]


def test_integer_prices_accepted() -> None:
    result = _check(_rows(0, ["2026-11-20", 228, 231, 227, 230, 229, 51234000]))

    assert result.violations == []
    assert result.bars[0][1] == 228.0


# --- Fichier vide, forme, dates (T5) -----------------------------------------------------------

BLOCKING_CASES_T5: dict[str, tuple[list[Any], list[tuple[date | None, str]]]] = {
    "fichier vide": ([], [(None, "empty_bars")]),
    "6 éléments": (
        _rows(1, ["2026-11-23", 231.0, 233.12, 229.6, 232.4, 48765000]),
        [(date(2026, 11, 23), "schema")],
    ),
    "ligne qui n'est pas une liste": (_rows(1, {"date": "2026-11-23"}), [(None, "schema")]),
    "chaîne à la place d'un prix": (
        _rows(1, ["2026-11-23", "231.0", 233.12, 229.6, 232.4, 231.1734, 48765000]),
        [(date(2026, 11, 23), "schema")],
    ),
    "booléen à la place d'un prix": (
        _rows(1, ["2026-11-23", True, 233.12, 229.6, 232.4, 231.1734, 48765000]),
        [(date(2026, 11, 23), "schema")],
    ),
    "volume non entier": (
        _rows(1, ["2026-11-23", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000.5]),
        [(date(2026, 11, 23), "schema")],
    ),
    "date illisible": (
        _rows(1, ["23/11/2026", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000]),
        [(None, "schema")],
    ),
    "date dupliquée": (
        _rows(1, ["2026-11-20", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000]),
        [(date(2026, 11, 20), "dates_not_increasing")],
    ),
    "date décroissante": (
        [VALID_ROWS[1], VALID_ROWS[0], VALID_ROWS[2]],
        [(date(2026, 11, 20), "dates_not_increasing")],
    ),
    "samedi": (
        _rows(1, ["2026-11-21", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000]),
        [(date(2026, 11, 21), "non_session_date")],
    ),
    "Thanksgiving": (
        [*VALID_ROWS, ["2026-11-26", 233.5, 235.0, 232.0, 234.0, 232.7643, 1]],
        [(date(2026, 11, 26), "non_session_date"), (date(2026, 11, 26), "after_last_session")],
    ),
    "hors plage du calendrier": (
        [["1985-01-02", 1.0, 1.5, 0.5, 1.2, 1.1, 100], *VALID_ROWS],
        [(date(1985, 1, 2), "non_session_date")],
    ),
    "barre après S": (
        [*VALID_ROWS, ["2026-11-25", 233.5, 235.0, 232.0, 234.0, 232.7643, 1]],
        [(date(2026, 11, 25), "after_last_session")],
    ),
}


@pytest.mark.parametrize(
    ("rows", "expected"), list(BLOCKING_CASES_T5.values()), ids=list(BLOCKING_CASES_T5)
)
def test_blocking_rule(rows: list[Any], expected: list[tuple[date | None, str]]) -> None:
    result = _check(rows)

    assert _rules(result) == expected
    assert result.bars == []  # aucune barre renvoyée dès qu'il y a une violation


def test_violation_carries_symbol_and_detail() -> None:
    result = _check(
        _rows(1, ["2026-11-20", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000]), symbol="MSFT"
    )

    violation = result.violations[0]
    assert violation.symbol == "MSFT"
    assert "2026-11-20" in violation.detail


def test_schema_error_does_not_stop_following_rows() -> None:
    rows = _rows(0, ["2026-11-20", "x", 231.45, 227.8, 230.95, 229.7312, 51234000])
    rows.append(["2026-11-25", 233.5, 235.0, 232.0, 234.0, 232.7643, 1])

    assert _rules(_check(rows)) == [
        (date(2026, 11, 20), "schema"),
        (date(2026, 11, 25), "after_last_session"),
    ]


# --- Prix, volume, OHLC (T6) -------------------------------------------------------------------

NAN = float("nan")
INF = float("inf")
D23 = date(2026, 11, 23)


def _row23(**changes: Any) -> list[Any]:
    """Ligne valide du 23/11/2026, modifiée par position nommée."""
    values: dict[str, Any] = {
        "open": 231.0,
        "high": 233.12,
        "low": 229.6,
        "close": 232.4,
        "adj_close": 231.1734,
        "volume": 48765000,
    }
    values.update(changes)
    return ["2026-11-23", *values.values()]


BLOCKING_CASES_T6: dict[str, tuple[list[Any], list[tuple[date | None, str]]]] = {
    "prix à 0": (_rows(1, _row23(open=0.0, low=0.0)), [(D23, "non_positive_price")]),
    "prix négatif": (_rows(1, _row23(adj_close=-1.5)), [(D23, "non_positive_price")]),
    "NaN": (_rows(1, _row23(close=NAN)), [(D23, "non_positive_price")]),
    "NaN sur adj_close": (_rows(1, _row23(adj_close=NAN)), [(D23, "non_positive_price")]),
    "Infinity": (_rows(1, _row23(high=INF)), [(D23, "non_positive_price")]),
    "prix non arrondi": (_rows(1, _row23(adj_close=231.17345)), [(D23, "not_rounded")]),
    "volume négatif": (_rows(1, _row23(volume=-1)), [(D23, "negative_volume")]),
    "high < low": (_rows(1, _row23(high=229.0)), [(D23, "ohlc_inconsistent")]),
    "low > open": (_rows(1, _row23(low=231.5)), [(D23, "ohlc_inconsistent")]),
    "high < close": (_rows(1, _row23(high=232.0)), [(D23, "ohlc_inconsistent")]),
}


@pytest.mark.parametrize(
    ("rows", "expected"), list(BLOCKING_CASES_T6.values()), ids=list(BLOCKING_CASES_T6)
)
def test_blocking_rule_prices(rows: list[Any], expected: list[tuple[date | None, str]]) -> None:
    result = _check(rows)

    assert _rules(result) == expected
    assert result.bars == []


def test_zero_volume_is_not_blocking() -> None:
    result = _check(_rows(1, _row23(volume=0)))

    assert result.violations == []
    assert result.bars[1][6] == 0


def test_ohlc_equal_bounds_accepted() -> None:
    result = _check(_rows(1, _row23(open=229.6, low=229.6, close=233.12, high=233.12)))

    assert result.violations == []


def test_all_violations_reported_not_only_first() -> None:
    rows = [
        ["2026-11-20", 228.1, 227.0, 227.8, 230.95, 229.7312, 51234000],  # high < low
        _row23(volume=-5),
        ["2026-11-24", 232.4, 234.0, 231.0, 233.5, 0.0, 45000000],
    ]

    assert _rules(_check(rows)) == [
        (date(2026, 11, 20), "ohlc_inconsistent"),
        (D23, "negative_volume"),
        (date(2026, 11, 24), "non_positive_price"),
    ]


def test_multiple_rules_on_same_row() -> None:
    """Date dupliquée et `high < low` sur la même ligne : deux violations."""
    rows = _rows(1, ["2026-11-20", 231.0, 229.0, 229.6, 232.4, 231.1734, 48765000])

    assert _rules(_check(rows)) == [
        (date(2026, 11, 20), "dates_not_increasing"),
        (date(2026, 11, 20), "ohlc_inconsistent"),
    ]


def test_ohlc_consistent_shared_with_bars() -> None:
    """F01 (nettoyage) et F02 (validation) appliquent le même prédicat OHLC."""
    assert bars.ohlc_consistent is quality.ohlc_consistent
    assert quality.ohlc_consistent(open_=10.0, high=11.0, low=9.0, close=10.5)
    assert not quality.ohlc_consistent(open_=10.0, high=10.2, low=9.0, close=10.5)
    assert not quality.ohlc_consistent(open_=10.0, high=11.0, low=10.1, close=10.5)


# --- Avertissements large_move et zero_volume (T7) ---------------------------------------------


def _bars(closes: list[float], *, end: date = S, volumes: list[int] | None = None) -> list[Bar]:
    """Barres sur les dernières séances jusqu'à `end`, avec les `closes` donnés (OHLC cohérents)."""
    days = CAL.sessions(CAL.shift(end, -(len(closes) - 1)), end)
    vols = volumes if volumes is not None else [1_000_000] * len(closes)
    return [
        (day, close, close * 1.01, close * 0.99, close, close, vol)
        for day, close, vol in zip(days, closes, vols, strict=True)
    ]


@pytest.mark.parametrize(
    ("new_close", "expected_value"),
    [(160.0, 0.6), (70.0, -0.3), (135.0, None), (140.0, None), (71.4, -0.286)],
    ids=[
        "+60%→avertissement",
        "-30%→avertissement",
        "+35%→rien",
        "+40%→rien (seuil strict)",
        "-28,6%→avertissement (|ln| > ln 1,4)",
    ],
)
def test_large_move_thresholds(new_close: float, expected_value: float | None) -> None:
    bars = _bars([100.0, new_close])

    warnings = large_moves("AAPL", bars, since=bars[0][0])

    if expected_value is None:
        assert warnings == []
    else:
        assert [(w.rule, w.start, w.end, w.value) for w in warnings] == [
            ("large_move", S, S, expected_value)
        ]
        assert warnings[0].symbol == "AAPL"


def test_large_move_threshold_constant() -> None:
    assert math.isclose(LARGE_MOVE_LOG, math.log(1.4))


def test_large_move_only_since_window_start() -> None:
    """La barre `t` doit être dans la fenêtre ; `t-1` peut la précéder."""
    bars = _bars([100.0, 200.0, 200.0, 400.0])  # sauts aux barres 1 et 3

    warnings = large_moves("AAPL", bars, since=bars[3][0])

    assert [w.start for w in warnings] == [bars[3][0]]
    assert len(large_moves("AAPL", bars, since=bars[0][0])) == 2


def test_large_move_single_bar_none() -> None:
    assert large_moves("AAPL", _bars([100.0]), since=date(2026, 1, 1)) == []


def test_zero_volume_warns_each_bar_in_window() -> None:
    bars = _bars([100.0] * 4, volumes=[0, 5, 0, 0])

    warnings = zero_volumes("SPY", bars, since=bars[1][0])

    assert [(w.rule, w.start, w.end, w.value) for w in warnings] == [
        ("zero_volume", bars[2][0], bars[2][0], None),
        ("zero_volume", bars[3][0], bars[3][0], None),
    ]
