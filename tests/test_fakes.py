"""Tests des doublures de test (`tests/fakes.py`) : elles doivent respecter le contrat
`PriceSource` pour que les tests d'ingestion soient significatifs."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from fakes import FakeClock, FakePriceSource, RecordingSleep, make_bars
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.source import PriceSource, RawBar, SourceError
from tradinghelper.schemas import PricesFile

CAL = NyseCalendar()


def _source(**kwargs: object) -> FakePriceSource:
    data = {
        "AAPL": make_bars(CAL, date(2026, 11, 16), date(2026, 11, 27), base=200.0),
        "MSFT": make_bars(CAL, date(2026, 11, 16), date(2026, 11, 27), base=400.0),
    }
    return FakePriceSource(data, **kwargs)  # type: ignore[arg-type]


def test_fake_source_satisfies_protocol() -> None:
    source: PriceSource = _source()

    assert isinstance(source, FakePriceSource)


def test_make_bars_on_sessions_and_valid_after_rounding() -> None:
    bars = make_bars(CAL, date(2026, 11, 23), date(2026, 11, 30), base=100.0)

    assert [bar.date for bar in bars] == CAL.sessions(date(2026, 11, 23), date(2026, 11, 30))
    rows = [
        (
            b.date,
            round(b.open, 4),
            round(b.high, 4),
            round(b.low, 4),
            round(b.close, 4),
            round(b.adj_close, 4),
            int(b.volume),
        )
        for b in bars
    ]
    PricesFile.model_validate(
        {
            "schema_version": 1,
            "symbol": "AAPL",
            "currency": "USD",
            "source": "yfinance",
            "columns": ["date", "open", "high", "low", "close", "adj_close", "volume"],
            "last_updated": "2026-11-30T22:00:00Z",
            "bars": rows,
        }
    )
    assert all(b.adj_close != b.close for b in bars)


def test_make_bars_deterministic() -> None:
    first = make_bars(CAL, date(2026, 11, 2), date(2026, 11, 27), base=50.0)

    assert first == make_bars(CAL, date(2026, 11, 2), date(2026, 11, 27), base=50.0)


def test_fetch_filters_dates_inclusive_and_logs_calls() -> None:
    source = _source()

    result = source.fetch(["AAPL", "MSFT"], date(2026, 11, 24), date(2026, 11, 25))

    assert {s: [b.date for b in bars] for s, bars in result.items()} == {
        "AAPL": [date(2026, 11, 24), date(2026, 11, 25)],
        "MSFT": [date(2026, 11, 24), date(2026, 11, 25)],
    }
    assert source.calls == [(("AAPL", "MSFT"), date(2026, 11, 24), date(2026, 11, 25))]


def test_missing_symbol_omitted() -> None:
    source = _source(missing={"MSFT"})

    result = source.fetch(["AAPL", "MSFT"], date(2026, 11, 24), date(2026, 11, 25))

    assert set(result) == {"AAPL"}


def test_no_data_at_all_raises_like_real_source() -> None:
    source = _source(missing={"AAPL"})

    with pytest.raises(SourceError):
        source.fetch(["AAPL"], date(2026, 11, 24), date(2026, 11, 25))


def test_fail_times_then_succeeds() -> None:
    source = _source(fail_times={"AAPL": 2})

    for _ in range(2):
        with pytest.raises(ConnectionError):
            source.fetch(["AAPL"], date(2026, 11, 24), date(2026, 11, 25))

    assert set(source.fetch(["AAPL"], date(2026, 11, 24), date(2026, 11, 25))) == {"AAPL"}


def test_always_fail_raises_even_in_batch() -> None:
    source = _source(always_fail={"MSFT"})

    with pytest.raises(ConnectionError, match="MSFT"):
        source.fetch(["AAPL", "MSFT"], date(2026, 11, 24), date(2026, 11, 25))
    assert set(source.fetch(["AAPL"], date(2026, 11, 24), date(2026, 11, 25))) == {"AAPL"}


def test_extra_bars_returned_as_is() -> None:
    weird = RawBar(date(2026, 11, 28), 1.0, 2.0, 0.5, 1.5, 1.5, 10.0)  # samedi
    source = _source(extra={"AAPL": [weird]})

    result = source.fetch(["AAPL"], date(2026, 11, 27), date(2026, 11, 30))

    assert weird in result["AAPL"]


def test_fake_clock_and_recording_sleep() -> None:
    clock = FakeClock(datetime(2026, 11, 24, 22, 30, tzinfo=UTC))
    sleep = RecordingSleep()

    assert clock() == datetime(2026, 11, 24, 22, 30, tzinfo=UTC)
    clock.now = datetime(2026, 11, 25, 22, 30, tzinfo=UTC)
    assert clock().day == 25
    sleep(2.0)
    sleep(4.0)
    assert sleep.delays == [2.0, 4.0]
