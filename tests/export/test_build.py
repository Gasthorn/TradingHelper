"""Tests de la construction pure des fichiers d'export (F08 — R6, R9 à R12, R14, R15)."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date

import numpy as np
import pytest
from pydantic import BaseModel

from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.export.build import (
    MONEY_DECIMALS,
    PRICE_DECIMALS,
    RATIO_DECIMALS,
    RSI_DECIMALS,
    build_overview,
    build_ticker,
    collect_markers,
    compute_data_as_of,
    digest,
    render,
    rounded,
)
from tradinghelper.features.indicators import bollinger, rsi_wilder, sma
from tradinghelper.schemas import (
    PRICE_COLUMNS,
    SPARK_LENGTH,
    ExportMarker,
    HealthRun,
    HealthValidate,
    PricesFile,
    SignalsFile,
    TickerSeries,
)

# --- Rendu, empreinte, arrondi (T9) ------------------------------------------------------------


class _Sample(BaseModel):
    label: str
    value: float
    day: date
    items: list[int]


def test_decimal_grid_matches_spec() -> None:
    """Grille d'arrondi des Définitions de la spec (R14)."""
    assert (PRICE_DECIMALS, RSI_DECIMALS, RATIO_DECIMALS, MONEY_DECIMALS) == (4, 2, 4, 2)


def test_render_is_minified_utf8() -> None:
    sample = _Sample(label="Société générale", value=1.5, day=date(2026, 11, 23), items=[1, 2])

    content = render(sample)

    expected = '{"label":"Société générale","value":1.5,"day":"2026-11-23","items":[1,2]}'
    assert content == expected.encode("utf-8")


def test_render_refuses_nan() -> None:
    """Seconde barrière (R8, R14) : un NaN qui aurait échappé au modèle ne s'écrit jamais."""
    with pytest.raises(ValueError, match="JSON"):
        render(_Sample(label="x", value=math.nan, day=date(2026, 11, 23), items=[]))


def test_render_uses_json_aliases() -> None:
    run = HealthRun(
        session_date=date(2026, 11, 23),
        ingest=None,
        validate_=HealthValidate(exit_code=0, violations=0, warnings=2),
    )

    payload = json.loads(render(run))

    assert payload["validate"] == {"exit_code": 0, "violations": 0, "warnings": 2}
    assert "validate_" not in payload


def test_render_is_deterministic() -> None:
    sample = _Sample(label="a", value=0.1, day=date(2026, 1, 2), items=[3])

    assert render(sample) == render(sample)


def test_digest_is_16_hex_of_sha256() -> None:
    content = b'{"a":1}'

    assert digest(content) == hashlib.sha256(content).hexdigest()[:16]
    assert len(digest(b"")) == 16


def test_rounded_nan_to_none() -> None:
    assert rounded(np.array([np.nan, 1.23456, np.nan]), 4) == [None, 1.2346, None]


@pytest.mark.parametrize(
    ("decimals", "values", "expected"),
    [
        (4, [0.1 + 0.2, 228.10000001, 0.123449999, 0.0987654], [0.3, 228.1, 0.1234, 0.0988]),
        (2, [61.4249, 63.875, 100.0, 0.0], [61.42, 63.88, 100.0, 0.0]),
    ],
)
def test_rounded_decimals(decimals: int, values: list[float], expected: list[float]) -> None:
    result = rounded(np.array(values), decimals)

    assert result == pytest.approx(expected)
    for value in result:
        assert value is not None
        assert round(value, decimals) == value, value


def test_rounded_returns_python_floats() -> None:
    result = rounded(np.array([1.0, np.nan]), 4)

    assert type(result[0]) is float
    assert json.dumps(result) == "[1.0, null]"


def test_rounded_empty() -> None:
    assert rounded(np.array([], dtype=np.float64), 4) == []


def test_rounded_refuses_infinity() -> None:
    with pytest.raises(ValueError, match="infini"):
        rounded(np.array([1.0, np.inf]), 4)


# --- Fiche ticker et marqueurs (T10) ------------------------------------------------------------

CAL = NyseCalendar()


def _prices(
    closes: list[float], *, symbol: str = "AAPL", first: date = date(2026, 1, 2)
) -> PricesFile:
    """Fichier de prix valide : une séance NYSE par clôture à partir de `first`, OHLC cohérents."""
    sessions = CAL.sessions(first, CAL.shift(first, len(closes) - 1)) if closes else []
    bars = []
    for i, (day, close) in enumerate(zip(sessions, closes, strict=True)):
        close = round(close, 4)
        open_ = round(close * 0.995, 4)
        high = round(max(open_, close) * 1.01, 4)
        low = round(min(open_, close) * 0.99, 4)
        bars.append((day, open_, high, low, close, round(close * 0.98, 4), 1_000_000 + i))
    return PricesFile.model_validate(
        {
            "schema_version": 1,
            "symbol": symbol,
            "currency": "USD",
            "source": "yfinance",
            "columns": list(PRICE_COLUMNS),
            "last_updated": "2026-11-23T22:41:05Z",
            "bars": bars,
        }
    )


def _closes(n: int) -> list[float]:
    """Série déterministe et non monotone (le RSI varie)."""
    return [100.0 + 10.0 * math.sin(i / 5.0) + 0.05 * i for i in range(n)]


def _signals_file(day: date, *signals: tuple[str, str, str, float]) -> SignalsFile:
    return SignalsFile.model_validate(
        {
            "schema_version": 1,
            "date": day.isoformat(),
            "generated_at": f"{day.isoformat()}T22:45:00Z",
            "signals": [
                {"strategy_id": strategy, "symbol": symbol, "action": action,
                 "confidence": confidence, "target_weight": 0.05, "horizon_days": 5}
                for strategy, symbol, action, confidence in signals
            ],
        }
    )  # fmt: skip


def test_ticker_columns_and_lengths() -> None:
    """R6 : colonnes du §7, sans `adj_close` ni milieu de Bollinger, toutes de même longueur."""
    ticker = build_ticker(_prices(_closes(250)), [])

    series = ticker.series.model_dump()
    assert list(series) == list(TickerSeries.model_fields)
    assert "adj_close" not in series
    assert {len(column) for column in series.values()} == {250}
    assert ticker.symbol == "AAPL"
    assert ticker.schema_version == 1


def test_ticker_ohlcv_copied_from_bars() -> None:
    prices = _prices(_closes(30))

    series = build_ticker(prices, []).series

    assert series.date == [bar[0] for bar in prices.bars]
    assert series.open == [bar[1] for bar in prices.bars]
    assert series.high == [bar[2] for bar in prices.bars]
    assert series.low == [bar[3] for bar in prices.bars]
    assert series.close == [bar[4] for bar in prices.bars]
    assert series.volume == [bar[6] for bar in prices.bars]


def test_ticker_indicators_match_functions_and_are_rounded() -> None:
    """Indicateurs sur `close` (R7), arrondis : prix à 4 décimales, RSI à 2 (R14)."""
    prices = _prices(_closes(250))
    close = np.array([bar[4] for bar in prices.bars])

    series = build_ticker(prices, []).series

    _middle, upper, lower = bollinger(close, 20, 2.0)
    assert series.sma20 == rounded(sma(close, 20), 4)
    assert series.sma50 == rounded(sma(close, 50), 4)
    assert series.sma200 == rounded(sma(close, 200), 4)
    assert series.bb_upper == rounded(upper, 4)
    assert series.bb_lower == rounded(lower, 4)
    assert series.rsi14 == rounded(rsi_wilder(close, 14), 2)
    assert all(v is None or round(v, 2) == v for v in series.rsi14)
    assert all(v is None or round(v, 4) == v for v in series.sma20 + series.bb_upper)


def test_short_history_sma200_all_null() -> None:
    series = build_ticker(_prices(_closes(50)), []).series

    assert series.sma200 == [None] * 50
    assert series.sma20[:19] == [None] * 19
    assert series.sma20[19] is not None
    assert series.rsi14[:14] == [None] * 14


def test_single_bar_ticker() -> None:
    series = build_ticker(_prices([123.45]), []).series

    assert series.close == [123.45]
    assert series.rsi14 == [None]


def test_no_nan_in_output() -> None:
    content = render(build_ticker(_prices(_closes(220)), []))

    assert b"NaN" not in content
    assert b"Infinity" not in content
    assert b"null" in content  # warm-up


def test_ticker_carries_given_markers() -> None:
    marker = ExportMarker(date=date(2026, 1, 5), strategy_id="s", action="BUY", confidence=0.6)

    assert build_ticker(_prices(_closes(5)), [marker]).markers == [marker]


def test_markers_buy_sell_only_sorted() -> None:
    """R9 : HOLD exclus ; tri par date puis `strategy_id`, quel que soit l'ordre des fichiers."""
    nov23 = (("zeta", "AAPL", "SELL", 0.61), ("alpha", "AAPL", "BUY", 0.7))
    files = [
        _signals_file(date(2026, 11, 23), *nov23),
        _signals_file(date(2026, 11, 21), ("alpha", "AAPL", "HOLD", 0.5)),
        _signals_file(date(2026, 11, 20), ("alpha", "AAPL", "BUY", 0.67)),
    ]

    markers = collect_markers(files, {"AAPL"})["AAPL"]

    assert [(m.date, m.strategy_id, m.action) for m in markers] == [
        (date(2026, 11, 20), "alpha", "BUY"),
        (date(2026, 11, 23), "alpha", "BUY"),
        (date(2026, 11, 23), "zeta", "SELL"),
    ]
    assert markers[0].confidence == 0.67


def test_markers_ignore_unexported_symbols() -> None:
    files = [
        _signals_file(date(2026, 11, 20), ("a", "TSLA", "BUY", 0.6), ("a", "MSFT", "SELL", 0.6))
    ]

    markers = collect_markers(files, {"AAPL", "MSFT"})

    assert markers == {"AAPL": [], "MSFT": [markers["MSFT"][0]]}
    assert "TSLA" not in markers


def test_markers_date_from_file() -> None:
    (marker,) = collect_markers(
        [_signals_file(date(2026, 11, 20), ("a", "AAPL", "BUY", 0.6))], {"AAPL"}
    )["AAPL"]

    assert marker.date == date(2026, 11, 20)


def test_markers_confidence_rounded() -> None:
    (marker,) = collect_markers(
        [_signals_file(date(2026, 11, 20), ("a", "AAPL", "BUY", 0.123456))], {"AAPL"}
    )["AAPL"]

    assert marker.confidence == 0.1235


def test_markers_without_signals() -> None:
    assert collect_markers([], {"AAPL", "SPY"}) == {"AAPL": [], "SPY": []}


# --- Accueil et `data_as_of` (T11) --------------------------------------------------------------


def test_overview_spark_60_values() -> None:
    prices = _prices(_closes(100))

    (ticker,) = build_overview({"AAPL": prices}, date(2026, 5, 27)).tickers

    assert ticker.spark == [bar[4] for bar in prices.bars[-SPARK_LENGTH:]]
    assert len(ticker.spark) == SPARK_LENGTH
    assert ticker.last_close == prices.bars[-1][4]


def test_overview_short_history_spark() -> None:
    prices = _prices(_closes(7))

    (ticker,) = build_overview({"AAPL": prices}, None).tickers

    assert ticker.spark == [bar[4] for bar in prices.bars]


def test_change_1d() -> None:
    prices = _prices([200.0, 210.5])

    (ticker,) = build_overview({"AAPL": prices}, None).tickers

    assert ticker.change_1d == 0.0525  # 210.5 / 200 - 1, arrondi à 4 décimales (R14)


def test_change_1d_rounded() -> None:
    (ticker,) = build_overview({"AAPL": _prices([3.0, 4.0])}, None).tickers

    assert ticker.change_1d == 0.3333


def test_change_1d_null_single_bar() -> None:
    (ticker,) = build_overview({"AAPL": _prices([123.45])}, None).tickers

    assert ticker.change_1d is None
    assert ticker.spark == [123.45]


def test_overview_keeps_given_symbol_order() -> None:
    prices = {
        "MSFT": _prices(_closes(3), symbol="MSFT"),
        "AAPL": _prices(_closes(3), symbol="AAPL"),
        "SPY": _prices(_closes(3), symbol="SPY"),
    }

    overview = build_overview(prices, None)

    assert [t.symbol for t in overview.tickers] == ["MSFT", "AAPL", "SPY"]


def test_overview_m1_sections_empty() -> None:
    overview = build_overview({"AAPL": _prices(_closes(3))}, date(2026, 1, 6))

    assert overview.schema_version == 1
    assert overview.data_as_of == date(2026, 1, 6)
    assert overview.leaderboard == []
    assert overview.latest_signals == []
    assert overview.kpis.best_strategy_30d is None


def test_overview_without_symbols() -> None:
    overview = build_overview({}, None)

    assert overview.tickers == []
    assert overview.data_as_of is None


def test_overview_refuses_empty_bars() -> None:
    with pytest.raises(ValueError, match="aucune barre"):
        build_overview({"AAPL": _prices([])}, None)


def test_data_as_of_is_min_last_date() -> None:
    """Définitions : date du symbole le plus en retard (vue prudente)."""
    last_dates = {"AAPL": date(2026, 11, 23), "MSFT": date(2026, 11, 19), "SPY": date(2026, 11, 23)}

    assert compute_data_as_of(last_dates) == date(2026, 11, 19)


def test_data_as_of_null_without_files() -> None:
    assert compute_data_as_of({}) is None
