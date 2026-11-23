"""Tests de l'orchestration de l'ingestion (F01). Aucun réseau : `FakePriceSource`,
vrai calendrier NYSE (hors ligne), horloge et `sleep` injectés."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from fakes import FakeClock, FakePriceSource, RecordingSleep, make_bars
from tradinghelper.config import UniverseConfig
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.ingest import (
    RETRY_DELAYS,
    IngestOutcome,
    IngestRequest,
    RetryError,
    ingest,
    with_retry,
)
from tradinghelper.data.source import RawBar
from tradinghelper.data.storage import dumps_prices, prices_path, read_prices
from tradinghelper.schemas import IngestTickerResult

# --- Relances avec backoff (R10) ---------------------------------------------------------------


class _Flaky:
    """Appel qui lève `failures` fois puis renvoie `"ok"`."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError(f"échec n°{self.calls}")
        return "ok"


def test_retry_delays_are_2_4_8() -> None:
    assert RETRY_DELAYS == (2.0, 4.0, 8.0)


def test_with_retry_first_try() -> None:
    sleep = RecordingSleep()
    call = _Flaky(0)

    assert with_retry(call, sleep) == ("ok", 1)
    assert sleep.delays == []
    assert call.calls == 1


def test_with_retry_succeeds_after_two_failures() -> None:
    sleep = RecordingSleep()
    call = _Flaky(2)

    assert with_retry(call, sleep) == ("ok", 3)
    assert sleep.delays == [2.0, 4.0]


def test_with_retry_succeeds_on_last_attempt() -> None:
    sleep = RecordingSleep()

    assert with_retry(_Flaky(3), sleep) == ("ok", 4)
    assert sleep.delays == [2.0, 4.0, 8.0]


def test_with_retry_gives_up_after_four_attempts() -> None:
    sleep = RecordingSleep()
    call = _Flaky(10)

    with pytest.raises(RetryError) as excinfo:
        with_retry(call, sleep)

    assert call.calls == 4
    assert sleep.delays == [2.0, 4.0, 8.0]
    assert excinfo.value.attempts == 4
    assert isinstance(excinfo.value.cause, ConnectionError)
    assert str(excinfo.value.cause) == "échec n°4"
    assert excinfo.value.__cause__ is excinfo.value.cause
    assert "échec n°4" in str(excinfo.value)


def test_with_retry_does_not_swallow_interrupts() -> None:
    sleep = RecordingSleep()

    def interrupted() -> str:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        with_retry(interrupted, sleep)
    assert sleep.delays == []


# --- Planification par ticker (R1, R2, R3, R9) -------------------------------------------------

CAL = NyseCalendar()
NOW = datetime(2026, 11, 24, 22, 30, tzinfo=UTC)  # S = 2026-11-24
S = date(2026, 11, 24)


def _universe(*tickers: tuple[str, date], benchmark: str = "SPY") -> UniverseConfig:
    # `today` injecté (comme `load_config`) : la validation de `start` ne dépend pas de l'horloge.
    return UniverseConfig.model_validate(
        {
            "currency": "USD",
            "benchmark": benchmark,
            "tickers": [
                {"symbol": symbol, "name": symbol, "sector": "Test", "start": start}
                for symbol, start in tickers
            ],
        },
        context={"today": date(2026, 12, 31)},
    )


UNIVERSE = _universe(("AAPL", date(2026, 10, 1)), ("MSFT", date(2026, 9, 1)))


def _history(*symbols: str) -> dict[str, list[RawBar]]:
    return {
        symbol: make_bars(CAL, date(2026, 1, 2), date(2026, 12, 31), base=100.0 + 50 * i)
        for i, symbol in enumerate(symbols)
    }


@dataclass
class _Env:
    root: Path
    source: FakePriceSource
    clock: FakeClock
    sleep: RecordingSleep

    def run(
        self, universe: UniverseConfig = UNIVERSE, request: IngestRequest | None = None
    ) -> IngestOutcome:
        return ingest(
            universe,
            request or IngestRequest(),
            source=self.source,
            calendar=CAL,
            now=self.clock,
            sleep=self.sleep,
            data_root=self.root,
        )

    def file(self, symbol: str) -> Path:
        return prices_path(self.root, symbol)


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    return _Env(
        root=tmp_path / "data",
        source=FakePriceSource(_history("AAPL", "MSFT", "SPY")),
        clock=FakeClock(NOW),
        sleep=RecordingSleep(),
    )


def _results(outcome: IngestOutcome) -> dict[str, IngestTickerResult]:
    return {result.symbol: result for result in outcome.run.tickers}


def test_initial_run_creates_all_files_including_benchmark(env: _Env) -> None:
    assert not env.root.exists()

    outcome = env.run()

    assert outcome.session == S
    assert outcome.changed is True
    results = _results(outcome)
    assert list(results) == ["AAPL", "MSFT", "SPY"]
    for symbol, start in (("AAPL", date(2026, 10, 1)), ("MSFT", date(2026, 9, 1))):
        prices = read_prices(env.file(symbol))
        assert prices is not None
        assert prices.bars[0][0] == CAL.sessions(start, S)[0]
        assert prices.bars[-1][0] == S
        assert len(prices.bars) == len(CAL.sessions(start, S))
        assert env.file(symbol).read_bytes().decode("utf-8") == dumps_prices(prices)
        result = results[symbol]
        assert (result.status, result.mode, result.attempts) == ("ok", "initial", 1)
        assert result.bars_added == len(prices.bars)
        assert result.history_rewritten is False
    assert env.file("SPY").is_file()
    assert outcome.run.exit_code == 0


def test_benchmark_start_is_min_ticker_start(env: _Env) -> None:
    env.run()

    spy_calls = [call for call in env.source.calls if "SPY" in call[0]]
    assert spy_calls
    assert all(start == date(2026, 9, 1) and end == S for _, start, end in spy_calls)
    prices = read_prices(env.file("SPY"))
    assert prices is not None
    assert prices.bars[0][0] == date(2026, 9, 1)


def test_benchmark_listed_in_tickers_is_ingested_once(env: _Env) -> None:
    universe = _universe(("AAPL", date(2026, 10, 1)), ("SPY", date(2026, 11, 2)))

    outcome = env.run(universe)

    assert [r.symbol for r in outcome.run.tickers] == ["AAPL", "SPY"]


def test_file_outside_universe_untouched(env: _Env) -> None:
    other = env.file("XOM")
    other.parent.mkdir(parents=True)
    other.write_bytes(b"ne pas toucher")

    outcome = env.run()

    assert other.read_bytes() == b"ne pas toucher"
    assert "XOM" not in _results(outcome)


def test_empty_initial_response_fails(env: _Env) -> None:
    env.source.missing.add("MSFT")

    outcome = env.run()

    msft = _results(outcome)["MSFT"]
    assert (msft.status, msft.mode, msft.attempts) == ("failed", "initial", 4)
    assert msft.error is not None
    assert not env.file("MSFT").exists()
    assert _results(outcome)["AAPL"].status == "ok"
    assert env.sleep.delays == [2.0, 4.0, 8.0]


def test_second_run_same_session_makes_no_call_and_no_change(env: _Env) -> None:
    env.run()
    snapshot = {p: p.read_bytes() for p in env.root.rglob("*.json")}
    env.source.calls.clear()
    env.clock.now = NOW + timedelta(hours=1)

    outcome = env.run()

    assert env.source.calls == []
    assert {p: p.read_bytes() for p in env.root.rglob("*.json")} == snapshot
    assert outcome.changed is False
    assert outcome.should_report is False
    assert {(r.status, r.mode, r.attempts) for r in outcome.run.tickers} == {("unchanged", None, 0)}
    assert outcome.run.exit_code == 0


def test_corrupted_file_not_overwritten_and_message_mentions_full(env: _Env) -> None:
    corrupted = env.file("AAPL")
    corrupted.parent.mkdir(parents=True)
    corrupted.write_bytes(b"{pas du json")

    outcome = env.run()

    aapl = _results(outcome)["AAPL"]
    assert (aapl.status, aapl.mode, aapl.attempts) == ("failed", None, 0)
    assert aapl.error is not None
    assert "th ingest --symbols AAPL --full" in aapl.error
    assert corrupted.read_bytes() == b"{pas du json"
    assert all(call[0] != ("AAPL",) and "AAPL" not in call[0] for call in env.source.calls)
    assert _results(outcome)["MSFT"].status == "ok"
    assert outcome.should_report is True


def test_ticker_starting_after_last_session_is_unchanged(env: _Env) -> None:
    universe = _universe(("AAPL", date(2026, 10, 1)), ("NEW", date(2026, 11, 25)))
    env.clock.now = datetime(2026, 11, 25, 15, 0, tzinfo=UTC)  # S = 24/11, NEW démarre le 25

    outcome = env.run(universe)

    new = _results(outcome)["NEW"]
    assert (new.status, new.mode, new.attempts) == ("unchanged", None, 0)
    assert not env.file("NEW").exists()


def test_run_timestamps_and_args(env: _Env) -> None:
    outcome = env.run()

    assert outcome.run.started_at == NOW
    assert outcome.run.finished_at >= outcome.run.started_at
    assert outcome.run.duration_s == 0.0
    assert outcome.run.args.model_dump() == {"symbols": None, "full": False, "start": None}
