"""Tests de l'adaptateur yfinance (F01 — R5, R12, R16). `yf.download` est simulé : aucun réseau.

Le DataFrame simulé reproduit la forme renvoyée par `yf.download(group_by="ticker",
multi_level_index=True)` : colonnes MultiIndex (Ticker, Price), index de dates sans fuseau
(`ignore_tz` vaut True en journalier), colonnes entièrement NaN pour un ticker en échec.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import pandas as pd
import pytest

from tradinghelper.data import source as source_module
from tradinghelper.data.source import RawBar, SourceError, YFinanceSource, to_provider_symbol

FIELDS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


def _frame(per_ticker: dict[str, list[tuple[str, list[float]]]], tz: str | None = None) -> Any:
    """DataFrame façon `yf.download` : {ticker: [(date, [o, h, l, c, adj, vol]), ...]}."""
    dates = sorted({d for rows in per_ticker.values() for d, _ in rows})
    index = pd.DatetimeIndex(pd.to_datetime(dates), name="Date")
    if tz is not None:
        index = index.tz_localize(tz)
    columns = pd.MultiIndex.from_product([list(per_ticker), FIELDS], names=["Ticker", "Price"])
    frame = pd.DataFrame(float("nan"), index=index, columns=columns)
    for ticker, rows in per_ticker.items():
        for day, values in rows:
            position = dates.index(day)
            for field, value in zip(FIELDS, values, strict=True):
                frame.iloc[position, frame.columns.get_loc((ticker, field))] = value
    return frame


class _Recorder:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    def __call__(self, tickers: Any, **kwargs: Any) -> Any:
        self.calls.append((tickers, kwargs))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.fixture
def fake_download(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(result: Any) -> _Recorder:
        recorder = _Recorder(result)
        monkeypatch.setattr(source_module.yf, "download", recorder)
        return recorder

    return install


AAPL_ROWS = [
    ("2026-11-20", [228.1, 231.45, 227.8, 230.95, 229.7312, 51234000.0]),
    ("2026-11-23", [231.0, 233.12, 229.6, 232.4, 231.1734, 48765000.0]),
]


@pytest.mark.parametrize(
    ("symbol", "expected"), [("BRK.B", "BRK-B"), ("AAPL", "AAPL"), ("BF.B", "BF-B")]
)
def test_dot_symbol_mapped_to_dash(symbol: str, expected: str) -> None:
    assert to_provider_symbol(symbol) == expected


def test_download_called_with_explicit_parameters(fake_download: Any) -> None:
    recorder = fake_download(_frame({"AAPL": AAPL_ROWS, "BRK-B": AAPL_ROWS}))

    YFinanceSource().fetch(["AAPL", "BRK.B"], date(2026, 11, 16), date(2026, 11, 23))

    assert len(recorder.calls) == 1
    tickers, kwargs = recorder.calls[0]
    assert tickers == ["AAPL", "BRK-B"]
    assert kwargs["start"] == "2026-11-16"
    assert kwargs["end"] == "2026-11-24"  # yfinance : borne de fin exclue
    assert kwargs["auto_adjust"] is False
    assert kwargs["actions"] is False
    assert kwargs["progress"] is False
    assert kwargs["group_by"] == "ticker"
    assert kwargs["multi_level_index"] is True
    assert kwargs["interval"] == "1d"


def test_multiindex_frame_to_raw_bars(fake_download: Any) -> None:
    msft_rows = [("2026-11-23", [500.0, 505.0, 498.0, 503.5, 502.1, 20000000.0])]
    fake_download(_frame({"AAPL": AAPL_ROWS, "MSFT": msft_rows}))

    result = YFinanceSource().fetch(["AAPL", "MSFT"], date(2026, 11, 20), date(2026, 11, 23))

    assert set(result) == {"AAPL", "MSFT"}
    assert result["AAPL"] == [
        RawBar(date(2026, 11, 20), 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000.0),
        RawBar(date(2026, 11, 23), 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000.0),
    ]
    # Les dates propres à AAPL (lignes NaN pour MSFT) ne créent pas de barre MSFT.
    assert [bar.date for bar in result["MSFT"]] == [date(2026, 11, 23)]
    assert all(type(bar.date) is date for bar in result["AAPL"])
    assert all(type(bar.close) is float for bar in result["AAPL"])


def test_result_keyed_by_config_symbol(fake_download: Any) -> None:
    fake_download(_frame({"BRK-B": AAPL_ROWS}))

    result = YFinanceSource().fetch(["BRK.B"], date(2026, 11, 20), date(2026, 11, 23))

    assert list(result) == ["BRK.B"]


def test_tz_aware_index_to_session_date(fake_download: Any) -> None:
    fake_download(_frame({"AAPL": AAPL_ROWS}, tz="America/New_York"))

    result = YFinanceSource().fetch(["AAPL"], date(2026, 11, 20), date(2026, 11, 23))

    assert [bar.date for bar in result["AAPL"]] == [date(2026, 11, 20), date(2026, 11, 23)]


def test_partial_nan_row_kept_for_cleaning(fake_download: Any) -> None:
    rows = [("2026-11-20", [228.1, float("nan"), 227.8, 230.95, 229.7312, 51234000.0])]
    fake_download(_frame({"AAPL": rows}))

    bar = YFinanceSource().fetch(["AAPL"], date(2026, 11, 20), date(2026, 11, 20))["AAPL"][0]

    assert math.isnan(bar.high)
    assert bar.close == 230.95


def test_missing_or_all_nan_symbol_omitted(fake_download: Any) -> None:
    frame = _frame({"AAPL": AAPL_ROWS, "DEAD": []})
    fake_download(frame)

    result = YFinanceSource().fetch(
        ["AAPL", "DEAD", "GONE"], date(2026, 11, 20), date(2026, 11, 23)
    )

    assert set(result) == {"AAPL"}


def test_no_data_for_any_symbol_raises(fake_download: Any) -> None:
    """yf.download avale les erreurs (réseau, limitation de débit) et renvoie des colonnes
    vides : sans aucune donnée, l'appel est un échec, pour que la relance (R10) s'applique."""
    fake_download(_frame({"AAPL": [], "MSFT": []}))

    with pytest.raises(SourceError, match="AAPL"):
        YFinanceSource().fetch(["AAPL", "MSFT"], date(2026, 11, 20), date(2026, 11, 23))


@pytest.mark.parametrize("result", [None, pd.DataFrame()], ids=["None", "vide"])
def test_empty_download_raises(fake_download: Any, result: Any) -> None:
    fake_download(result)

    with pytest.raises(SourceError):
        YFinanceSource().fetch(["AAPL"], date(2026, 11, 20), date(2026, 11, 23))


def test_download_exception_propagates(fake_download: Any) -> None:
    fake_download(ConnectionError("réseau coupé"))

    with pytest.raises(ConnectionError, match="réseau coupé"):
        YFinanceSource().fetch(["AAPL"], date(2026, 11, 20), date(2026, 11, 23))


def test_empty_symbol_list_makes_no_call(fake_download: Any) -> None:
    recorder = fake_download(_frame({"AAPL": AAPL_ROWS}))

    assert YFinanceSource().fetch([], date(2026, 11, 20), date(2026, 11, 23)) == {}
    assert recorder.calls == []
