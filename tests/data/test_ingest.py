"""Tests de l'orchestration de l'ingestion (F01). Aucun réseau : `FakePriceSource`,
vrai calendrier NYSE (hors ligne), horloge et `sleep` injectés."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from fakes import FakeClock, FakePriceSource, RecordingSleep, make_bars
from tradinghelper.config import UniverseConfig
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.ingest import (
    BATCH_SIZE,
    RETRY_DELAYS,
    IngestOutcome,
    IngestRequest,
    RetryError,
    exit_code,
    ingest,
    with_retry,
)
from tradinghelper.data.source import RawBar
from tradinghelper.data.storage import dumps_prices, prices_path, read_prices
from tradinghelper.schemas import Bar, IngestTickerResult

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
    # 1 appel groupé (MSFT + SPY, même date de début) + 4 appels individuels.
    assert (msft.status, msft.mode, msft.attempts) == ("failed", "initial", 5)
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


# --- Lots et relances individuelles (R11, R10, R12) ---------------------------------------------


def test_batch_size_is_20() -> None:
    assert BATCH_SIZE == 20


def test_45_tickers_same_start_make_3_batch_calls(env: _Env) -> None:
    symbols = [f"T{i:02d}" for i in range(44)] + ["SPY"]
    env.source.data = _history(*symbols)
    universe = _universe(*((symbol, date(2026, 11, 2)) for symbol in symbols))

    outcome = env.run(universe)

    assert [len(call[0]) for call in env.source.calls] == [20, 20, 5]
    assert sorted(s for call in env.source.calls for s in call[0]) == sorted(symbols)
    assert {r.status for r in outcome.run.tickers} == {"ok"}
    assert {r.attempts for r in outcome.run.tickers} == {1}


def test_tickers_grouped_by_start_date(env: _Env) -> None:
    universe = _universe(
        ("AAPL", date(2026, 10, 1)), ("MSFT", date(2026, 9, 1)), ("SPY", date(2026, 10, 1))
    )

    env.run(universe)

    assert sorted((call[0], call[1]) for call in env.source.calls) == [
        (("AAPL", "SPY"), date(2026, 10, 1)),
        (("MSFT",), date(2026, 9, 1)),
    ]


class _BatchOmits(FakePriceSource):
    """Omet `flaky` des réponses groupées, mais le renvoie quand il est demandé seul."""

    def __init__(self, data: dict[str, list[RawBar]], flaky: str) -> None:
        super().__init__(data)
        self.flaky = flaky

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> Mapping[str, list[RawBar]]:
        result = dict(super().fetch(symbols, start, end))
        if len(symbols) > 1:
            result.pop(self.flaky, None)
        return result


def test_ticker_missing_from_batch_retried_alone(env: _Env) -> None:
    env.source = _BatchOmits(_history("AAPL", "MSFT", "SPY"), flaky="MSFT")
    universe = _universe(("AAPL", date(2026, 10, 1)), ("MSFT", date(2026, 10, 1)))

    outcome = env.run(universe)

    assert [call[0] for call in env.source.calls] == [("AAPL", "MSFT", "SPY"), ("MSFT",)]
    msft = _results(outcome)["MSFT"]
    assert (msft.status, msft.attempts) == ("ok", 2)  # 1 appel groupé + 1 appel individuel
    assert _results(outcome)["AAPL"].attempts == 1
    assert env.file("MSFT").is_file()
    assert env.sleep.delays == []


def test_ticker_always_missing_fails_after_individual_retries(env: _Env) -> None:
    env.source.missing.add("MSFT")
    universe = _universe(("AAPL", date(2026, 10, 1)), ("MSFT", date(2026, 10, 1)))

    outcome = env.run(universe)

    msft = _results(outcome)["MSFT"]
    assert (msft.status, msft.attempts) == ("failed", 5)  # 1 groupé + 4 individuels
    assert env.sleep.delays == [2.0, 4.0, 8.0]


def test_batch_failing_entirely_falls_back_to_individual(env: _Env) -> None:
    env.source.fail_times["AAPL"] = 4  # les 4 tentatives du lot échouent
    universe = _universe(("AAPL", date(2026, 10, 1)), ("MSFT", date(2026, 10, 1)))

    outcome = env.run(universe)

    calls = [call[0] for call in env.source.calls]
    assert calls[:4] == [("AAPL", "MSFT", "SPY")] * 4
    assert sorted(calls[4:]) == [("AAPL",), ("MSFT",), ("SPY",)]
    assert {r.status for r in outcome.run.tickers} == {"ok"}
    assert {r.attempts for r in outcome.run.tickers} == {5}  # 4 groupées + 1 individuelle
    assert env.sleep.delays == [2.0, 4.0, 8.0]


def test_one_failing_ticker_does_not_block_others(env: _Env) -> None:
    env.source.always_fail.add("MSFT")

    outcome = env.run()

    results = _results(outcome)
    assert results["AAPL"].status == "ok"
    assert results["SPY"].status == "ok"
    msft = results["MSFT"]
    assert msft.status == "failed"
    assert msft.error is not None
    assert "échec simulé pour MSFT" in msft.error
    assert env.file("AAPL").is_file()
    assert not env.file("MSFT").exists()
    assert outcome.run.exit_code == 0
    assert outcome.should_report is True


def test_dot_symbol_stored_under_config_name(env: _Env) -> None:
    env.source.data = _history("BRK.B", "SPY")
    universe = _universe(("BRK.B", date(2026, 11, 2)))

    outcome = env.run(universe)

    assert _results(outcome)["BRK.B"].status == "ok"
    assert env.file("BRK.B").name == "BRK.B.json"
    prices = read_prices(env.file("BRK.B"))
    assert prices is not None
    assert prices.symbol == "BRK.B"


# --- Mode incrémental, rattrapage et réécriture sur révision (R3, R4, R7, R6) -------------------

SOLO = _universe(("AAPL", date(2026, 10, 1)), benchmark="AAPL")  # un seul ticker, sans SPY


def _at(day: int, hour: int = 22, minute: int = 30) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def _bar_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.startswith('    ["')]


def _scaled(bars: list[RawBar], *, adj: float = 1.0, close: float = 1.0) -> list[RawBar]:
    return [
        RawBar(
            b.date,
            b.open * close,
            b.high * close,
            b.low * close,
            b.close * close,
            round(b.adj_close * adj, 4),
            b.volume,
        )
        for b in bars
    ]


def _stored_bar(env: _Env, day: date) -> Bar:
    prices = read_prices(env.file("AAPL"))
    assert prices is not None
    return next(bar for bar in prices.bars if bar[0] == day)


def _initial(env: _Env, universe: UniverseConfig = SOLO, day: int = 24) -> None:
    env.clock.now = _at(day)
    env.run(universe)
    env.source.calls.clear()
    env.sleep.delays.clear()


def test_one_new_session_adds_one_line(env: _Env) -> None:
    _initial(env, UNIVERSE)
    before = {s: _bar_lines(env.file(s)) for s in ("AAPL", "MSFT", "SPY")}
    env.clock.now = _at(25)

    outcome = env.run()

    for symbol, old_lines in before.items():
        new_lines = _bar_lines(env.file(symbol))
        assert len(new_lines) == len(old_lines) + 1
        # Seule la virgule de l'ancienne dernière ligne change ; barres existantes intactes.
        assert [x.rstrip(",") for x in new_lines[:-1]] == [x.rstrip(",") for x in old_lines]
        assert '"2026-11-25"' in new_lines[-1]
        result = _results(outcome)[symbol]
        assert (result.status, result.mode, result.bars_added, result.bars_revised) == (
            "ok",
            "incremental",
            1,
            0,
        )
    assert outcome.session == date(2026, 11, 25)


def test_three_missed_sessions_add_three_lines(env: _Env) -> None:
    _initial(env)
    before = len(_bar_lines(env.file("AAPL")))
    env.clock.now = _at(30)  # 25, 27, 30 (le 26 est férié)

    outcome = env.run(SOLO)

    assert len(_bar_lines(env.file("AAPL"))) == before + 3
    assert _results(outcome)["AAPL"].bars_added == 3


def test_request_starts_5_sessions_before_last_date(env: _Env) -> None:
    _initial(env)
    env.clock.now = _at(25)

    env.run(SOLO)

    assert env.source.calls == [(("AAPL",), date(2026, 11, 17), date(2026, 11, 25))]


def test_overlap_volume_revision_replaced_without_rewrite(env: _Env) -> None:
    _initial(env)
    env.source.data["AAPL"] = [
        RawBar(b.date, b.open, b.high, b.low, b.close, b.adj_close, 7.0)
        if b.date == date(2026, 11, 20)
        else b
        for b in env.source.data["AAPL"]
    ]
    env.clock.now = _at(25)

    outcome = env.run(SOLO)

    aapl = _results(outcome)["AAPL"]
    assert (aapl.bars_added, aapl.bars_revised, aapl.history_rewritten) == (1, 1, False)
    assert _stored_bar(env, date(2026, 11, 20))[6] == 7
    assert len(env.source.calls) == 1


def test_no_new_bar_when_expected_fails(env: _Env) -> None:
    _initial(env)
    before = env.file("AAPL").read_bytes()
    env.source.data["AAPL"] = [b for b in env.source.data["AAPL"] if b.date <= S]
    env.clock.now = _at(25)

    outcome = env.run(SOLO)

    aapl = _results(outcome)["AAPL"]
    assert (aapl.status, aapl.mode, aapl.attempts) == ("failed", "incremental", 1)
    assert aapl.error is not None
    assert "séances attendues" in aapl.error
    assert env.file("AAPL").read_bytes() == before
    assert outcome.run.exit_code == 1
    assert outcome.should_report is True


def test_revision_triggers_full_rewrite(env: _Env) -> None:
    _initial(env)
    env.source.data["AAPL"] = _scaled(env.source.data["AAPL"], adj=0.997)  # dividende 0,3 %
    env.clock.now = _at(25)

    outcome = env.run(SOLO)

    aapl = _results(outcome)["AAPL"]
    assert (aapl.status, aapl.history_rewritten, aapl.rewrite_reason) == ("ok", True, "revision")
    assert aapl.bars_added == 1
    assert aapl.bars_revised == len(CAL.sessions(date(2026, 10, 1), S))
    assert aapl.attempts == 2
    assert env.source.calls == [
        (("AAPL",), date(2026, 11, 17), date(2026, 11, 25)),
        (("AAPL",), date(2026, 10, 1), date(2026, 11, 25)),
    ]
    prices = read_prices(env.file("AAPL"))
    assert prices is not None
    expected = {b.date: round(b.adj_close, 4) for b in env.source.data["AAPL"]}
    assert all(bar[5] == expected[bar[0]] for bar in prices.bars)
    assert prices.bars[-1][0] == date(2026, 11, 25)


def test_rewrite_starts_at_min_of_universe_start_and_first_stored(env: _Env) -> None:
    # Historique stocké plus ancien que le `start` de l'univers (ex. backfill antérieur).
    early = _universe(("AAPL", date(2026, 9, 1)), benchmark="AAPL")
    _initial(env, early)
    env.source.data["AAPL"] = _scaled(env.source.data["AAPL"], close=0.5, adj=0.5)  # split 2:1
    env.clock.now = _at(25)

    outcome = env.run(SOLO)  # univers actuel : start = 1er octobre

    assert _results(outcome)["AAPL"].history_rewritten is True
    assert env.source.calls[-1] == (("AAPL",), date(2026, 9, 1), date(2026, 11, 25))
    prices = read_prices(env.file("AAPL"))
    assert prices is not None
    assert prices.bars[0][0] == date(2026, 9, 1)


class _FailsAlone(FakePriceSource):
    """Échoue sur tout appel ne visant qu'un symbole dont la date de début précède `cutoff`."""

    def __init__(self, data: dict[str, list[RawBar]], cutoff: date) -> None:
        super().__init__(data)
        self.cutoff = cutoff

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> Mapping[str, list[RawBar]]:
        if len(symbols) == 1 and start < self.cutoff:
            self.calls.append((tuple(symbols), start, end))
            raise ConnectionError("téléchargement complet impossible (simulé)")
        return super().fetch(symbols, start, end)


def test_failed_rewrite_keeps_old_file_bytes(env: _Env) -> None:
    _initial(env)
    before = env.file("AAPL").read_bytes()
    revised = {"AAPL": _scaled(env.source.data["AAPL"], adj=0.997)}
    env.source = _FailsAlone(revised, cutoff=date(2026, 11, 1))
    env.clock.now = _at(25)

    outcome = env.run(SOLO)

    aapl = _results(outcome)["AAPL"]
    assert (aapl.status, aapl.history_rewritten, aapl.attempts) == ("failed", False, 5)
    assert aapl.error is not None
    assert "simulé" in aapl.error
    assert env.file("AAPL").read_bytes() == before
    assert env.sleep.delays == [2.0, 4.0, 8.0]


class _AlwaysRevised(FakePriceSource):
    """Chaque appel renvoie un historique ajusté différent (yfinance qui « oscille »)."""

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> Mapping[str, list[RawBar]]:
        result = super().fetch(symbols, start, end)
        factor = 1 - 0.01 * len(self.calls)
        return {s: _scaled(bars, adj=factor) for s, bars in result.items()}


def test_at_most_one_rewrite_per_ticker(env: _Env) -> None:
    _initial(env)
    env.source = _AlwaysRevised(env.source.data)
    env.clock.now = _at(25)

    outcome = env.run(SOLO)

    assert _results(outcome)["AAPL"].history_rewritten is True
    assert len(env.source.calls) == 2  # incrémental + un seul téléchargement complet


def test_no_bar_for_unclosed_session(env: _Env) -> None:
    _initial(env, day=23)
    partial_bar = RawBar(date(2026, 11, 25), 300.0, 301.0, 299.0, 300.5, 300.5, 10.0)
    env.source.extra["AAPL"] = [partial_bar]
    env.clock.now = _at(25, 20, 0)  # 15 h ET : S = 24/11, la séance du 25 est en cours

    outcome = env.run(SOLO)

    prices = read_prices(env.file("AAPL"))
    assert prices is not None
    assert prices.bars[-1][0] == date(2026, 11, 24)
    assert [(w.date, w.rule) for w in outcome.run.warnings] == [
        (date(2026, 11, 25), "after_last_session")
    ]


def test_dirty_response_writes_only_valid_bars(env: _Env) -> None:
    _initial(env)
    stored_1120 = _stored_bar(env, date(2026, 11, 20))
    env.source.extra["AAPL"] = [
        RawBar(date(2026, 11, 22), 1.0, 2.0, 0.5, 1.5, 1.5, 10.0),  # dimanche
        RawBar(date(2026, 11, 20), 1.0, float("nan"), 0.5, 1.5, 1.5, 10.0),  # doublon NaN
    ]
    env.clock.now = _at(25)

    outcome = env.run(SOLO)

    aapl = _results(outcome)["AAPL"]
    assert (aapl.status, aapl.bars_added, aapl.history_rewritten) == ("ok", 1, False)
    assert _stored_bar(env, date(2026, 11, 20)) == stored_1120
    prices = read_prices(env.file("AAPL"))
    assert prices is not None
    assert date(2026, 11, 22) not in {b[0] for b in prices.bars}
    assert sorted((str(w.date), w.rule) for w in outcome.run.warnings) == [
        ("2026-11-20", "duplicate_date"),
        ("2026-11-20", "missing_overlap_bar"),
        ("2026-11-20", "nan"),
        ("2026-11-22", "non_session_date"),
    ]


# --- Backfill `full`, filtre `symbols`, code de sortie et rapport (R13, R14, R15) ---------------


def _snapshot(env: _Env, *symbols: str) -> dict[str, bytes]:
    return {symbol: env.file(symbol).read_bytes() for symbol in symbols}


def test_full_backfill_rewrites_only_requested_symbols(env: _Env) -> None:
    _initial(env, UNIVERSE)
    others = _snapshot(env, "MSFT", "SPY")
    env.clock.now = _at(24, 23)

    outcome = env.run(request=IngestRequest(symbols=("AAPL",), full=True, start=date(2026, 10, 15)))

    assert [r.symbol for r in outcome.run.tickers] == ["AAPL"]
    aapl = _results(outcome)["AAPL"]
    assert (aapl.status, aapl.mode) == ("ok", "full")
    assert (aapl.history_rewritten, aapl.rewrite_reason) == (True, "backfill")
    assert env.source.calls == [(("AAPL",), date(2026, 10, 15), S)]
    prices = read_prices(env.file("AAPL"))
    assert prices is not None
    assert prices.bars[0][0] == date(2026, 10, 15)  # 1re séance >= --start
    assert prices.bars[-1][0] == S
    assert _snapshot(env, "MSFT", "SPY") == others
    assert outcome.changed is True


def test_full_without_start_uses_universe_start_and_repairs_corrupted_file(env: _Env) -> None:
    corrupted = env.file("AAPL")
    corrupted.parent.mkdir(parents=True)
    corrupted.write_bytes(b"{corrompu")

    outcome = env.run(request=IngestRequest(symbols=("AAPL",), full=True))

    aapl = _results(outcome)["AAPL"]
    assert (aapl.status, aapl.mode, aapl.rewrite_reason) == ("ok", "full", "backfill")
    prices = read_prices(env.file("AAPL"))
    assert prices is not None
    assert prices.bars[0][0] == CAL.sessions(date(2026, 10, 1), S)[0]


def test_full_backfill_counts_added_and_revised(env: _Env) -> None:
    _initial(env)
    env.source.data["AAPL"] = [
        RawBar(b.date, b.open, b.high, b.low, b.close, b.adj_close, 3.0)
        if b.date == date(2026, 11, 20)
        else b
        for b in env.source.data["AAPL"]
    ]

    outcome = env.run(SOLO, IngestRequest(full=True, start=date(2026, 9, 1)))

    aapl = _results(outcome)["AAPL"]
    assert aapl.bars_added == len(CAL.sessions(date(2026, 9, 1), date(2026, 9, 30)))
    assert aapl.bars_revised == 1


def test_full_benchmark_uses_benchmark_start(env: _Env) -> None:
    env.run(request=IngestRequest(symbols=("SPY",), full=True))

    assert env.source.calls == [(("SPY",), date(2026, 9, 1), S)]


def test_symbols_filter_without_full_is_incremental(env: _Env) -> None:
    _initial(env, UNIVERSE)
    env.clock.now = _at(25)

    outcome = env.run(request=IngestRequest(symbols=("MSFT",)))

    assert [(r.symbol, r.mode) for r in outcome.run.tickers] == [("MSFT", "incremental")]
    assert [call[0] for call in env.source.calls] == [("MSFT",)]


def test_unknown_symbol_in_request_raises(env: _Env) -> None:
    with pytest.raises(ValueError, match="XOM"):
        env.run(request=IngestRequest(symbols=("XOM",)))
    assert env.source.calls == []


def _ticker_result(status: str, attempts: int) -> IngestTickerResult:
    return IngestTickerResult(
        symbol="AAPL",
        status=status,  # type: ignore[arg-type]
        mode=None if attempts == 0 else "incremental",
        bars_added=0,
        bars_revised=0,
        history_rewritten=False,
        rewrite_reason=None,
        attempts=attempts,
        error="boom" if status == "failed" else None,
    )


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ([("failed", 4), ("failed", 5)], 1),
        ([("failed", 4), ("ok", 1)], 0),
        ([("unchanged", 0), ("unchanged", 0)], 0),
        ([("failed", 0), ("unchanged", 0)], 0),
        ([("failed", 0), ("failed", 4)], 1),
        ([], 0),
    ],
    ids=[
        "all_attempted_failed",
        "partial",
        "none_attempted",
        "corrupted_only_not_attempted",
        "corrupted_plus_attempted_failed",
        "empty",
    ],
)
def test_exit_code(results: list[tuple[str, int]], expected: int) -> None:
    assert exit_code([_ticker_result(status, attempts) for status, attempts in results]) == expected


def test_should_report_when_changed(env: _Env) -> None:
    assert env.run().should_report is True


def test_should_report_when_failed_without_change(env: _Env) -> None:
    env.source.always_fail.update({"AAPL", "MSFT", "SPY"})

    outcome = env.run()

    assert outcome.changed is False
    assert outcome.should_report is True
    assert outcome.run.exit_code == 1


def test_should_not_report_when_nothing_happened(env: _Env) -> None:
    env.run()

    assert env.run().should_report is False


def test_ingest_run_fields(env: _Env) -> None:
    times = iter([NOW, NOW + timedelta(seconds=42)])
    request = IngestRequest(symbols=("AAPL", "SPY"), full=True, start=date(2026, 11, 2))

    outcome = ingest(
        UNIVERSE,
        request,
        source=env.source,
        calendar=CAL,
        now=lambda: next(times, NOW + timedelta(seconds=42)),
        sleep=env.sleep,
        data_root=env.root,
    )

    run = outcome.run
    assert run.started_at == NOW
    assert run.finished_at == NOW + timedelta(seconds=42)
    assert run.duration_s == 42.0
    assert run.args.model_dump() == {
        "symbols": ["AAPL", "SPY"],
        "full": True,
        "start": date(2026, 11, 2),
    }
    assert [r.symbol for r in run.tickers] == ["AAPL", "SPY"]


# --- Compléments ajoutés à la vérification (/spec-verify) --------------------------------------


def test_new_ticker_downloads_full_history_only_for_it(env: _Env) -> None:
    """Critère 2 : un ticker ajouté à l'univers est téléchargé depuis son `start` ;
    les fichiers existants ne changent pas."""
    _initial(env, UNIVERSE)
    snapshot = {s: env.file(s).read_bytes() for s in ("AAPL", "MSFT", "SPY")}
    env.source.data.update(_history("NVDA"))
    bigger = _universe(
        ("AAPL", date(2026, 10, 1)), ("MSFT", date(2026, 9, 1)), ("NVDA", date(2026, 8, 3))
    )
    env.clock.now = _at(24, 23)  # même séance S = 24/11

    outcome = env.run(bigger)

    nvda = _results(outcome)["NVDA"]
    assert (nvda.status, nvda.mode) == ("ok", "initial")
    prices = read_prices(env.file("NVDA"))
    assert prices is not None
    assert prices.bars[0][0] == date(2026, 8, 3)
    assert prices.bars[-1][0] == S
    # Le benchmark démarre désormais au 3 août, mais son fichier existant n'est pas réécrit.
    assert {s: env.file(s).read_bytes() for s in ("AAPL", "MSFT", "SPY")} == snapshot
    assert [call[0] for call in env.source.calls] == [("NVDA",)]


def test_half_day_bar_written_after_early_close(env: _Env) -> None:
    """Critère 9 : demi-séance du 27/11/2026 (clôture 13 h ET), barre écrite à 13 h 45 ET."""
    _initial(env, day=25)
    env.clock.now = datetime(2026, 11, 27, 18, 45, tzinfo=UTC)  # 13 h 45 ET

    outcome = env.run(SOLO)

    assert outcome.session == date(2026, 11, 27)
    prices = read_prices(env.file("AAPL"))
    assert prices is not None
    assert prices.bars[-1][0] == date(2026, 11, 27)
    assert _results(outcome)["AAPL"].bars_added == 1
