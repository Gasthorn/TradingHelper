"""Tests de la commande `th ingest` (F01 — R13, R14, R15, R16).

`CliRunner` avec une config temporaire (`TH_CONFIG_DIR`), un dossier de données temporaire
(`TH_DATA_DIR`), et la source, l'horloge et `sleep` remplacés : aucun réseau, aucune attente.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from fakes import FakeClock, FakePriceSource, RecordingSleep, make_bars
from tradinghelper import cli
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.storage import prices_path, read_prices, run_report_path
from tradinghelper.schemas import RunReport

from conftest import WriteConfig

CAL = NyseCalendar()
NOW = datetime(2026, 11, 24, 22, 30, tzinfo=UTC)  # S = 2026-11-24
S = date(2026, 11, 24)

UNIVERSE = {
    "currency": "USD",
    "benchmark": "SPY",
    "tickers": [
        {"symbol": "AAPL", "name": "Apple", "sector": "Tech", "start": date(2026, 10, 1)},
        {"symbol": "MSFT", "name": "Microsoft", "sector": "Tech", "start": date(2026, 10, 1)},
    ],
}


@dataclass
class _Cli:
    data: Path
    source: FakePriceSource
    clock: FakeClock
    sleep: RecordingSleep
    runner: CliRunner

    def __call__(self, *args: str) -> Result:
        return self.runner.invoke(cli.app, ["ingest", *args])

    def file(self, symbol: str) -> Path:
        return prices_path(self.data, symbol)

    def reports(self) -> list[Path]:
        runs = self.data / "runs"
        return sorted(runs.iterdir()) if runs.exists() else []


@pytest.fixture
def th(tmp_path: Path, write_config: WriteConfig, monkeypatch: pytest.MonkeyPatch) -> _Cli:
    config_dir = write_config(universe=UNIVERSE)
    data = tmp_path / "data"
    monkeypatch.setenv("TH_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("TH_DATA_DIR", str(data))
    history = {
        symbol: make_bars(CAL, date(2026, 1, 2), date(2026, 12, 31), base=100.0 + 50 * i)
        for i, symbol in enumerate(["AAPL", "MSFT", "SPY"])
    }
    env = _Cli(data, FakePriceSource(history), FakeClock(NOW), RecordingSleep(), CliRunner())
    monkeypatch.setattr(cli, "_make_source", lambda: env.source)
    monkeypatch.setattr(cli, "_now", env.clock)
    monkeypatch.setattr(cli, "_sleep", env.sleep)
    return env


def test_ingest_listed_in_help(th: _Cli) -> None:
    result = th.runner.invoke(cli.app, ["--help"])

    assert "ingest" in result.stdout
    assert "schemas" in result.stdout


def test_ingest_writes_prices_and_report_on_change(th: _Cli) -> None:
    result = th()

    assert result.exit_code == 0, result.output
    for symbol in ("AAPL", "MSFT", "SPY"):
        assert read_prices(th.file(symbol)) is not None
    report_file = run_report_path(th.data, S)
    assert th.reports() == [report_file]
    report = RunReport.model_validate_json(report_file.read_text(encoding="utf-8"))
    assert report.session_date == S
    (run,) = report.ingest
    assert [t.symbol for t in run.tickers] == ["AAPL", "MSFT", "SPY"]
    assert run.exit_code == 0
    assert "2026-11-24" in result.stdout
    assert report_file.name in result.stdout


def test_no_report_on_holiday_or_second_run(th: _Cli) -> None:
    th()
    report_file = run_report_path(th.data, S)
    first_report = report_file.read_bytes()
    th.source.calls.clear()
    th.clock.now = datetime(2026, 11, 24, 23, 30, tzinfo=UTC)  # 2e run, même séance

    result = th()

    assert result.exit_code == 0, result.output
    assert th.source.calls == []
    assert th.reports() == [report_file]
    assert report_file.read_bytes() == first_report
    assert "aucun rapport" in result.stdout


def test_holiday_run_after_up_to_date_makes_no_change(th: _Cli) -> None:
    th.clock.now = datetime(2026, 11, 25, 22, 30, tzinfo=UTC)
    th()
    snapshot = {p: p.read_bytes() for p in th.data.rglob("*.json")}
    th.source.calls.clear()
    th.clock.now = datetime(2026, 11, 26, 23, 0, tzinfo=UTC)  # Thanksgiving

    result = th()

    assert result.exit_code == 0
    assert th.source.calls == []
    assert {p: p.read_bytes() for p in th.data.rglob("*.json")} == snapshot


def test_report_named_after_session_not_utc_date(th: _Cli) -> None:
    th.clock.now = datetime(2026, 11, 25, 0, 30, tzinfo=UTC)  # cron retardé après minuit UTC

    result = th()

    assert result.exit_code == 0, result.output
    assert th.reports() == [run_report_path(th.data, date(2026, 11, 24))]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--start", "2015-01-01"], "--full"),
        (["--symbols", "AAPL,XOM"], "XOM"),
        (["--full", "--start", "2026-13-01"], "2026-13-01"),
        (["--full", "--start", "hier"], "hier"),
        (["--full", "--start", "2026-12-01"], "futur"),
        (["--symbols", " , "], "--symbols"),
    ],
    ids=[
        "start_without_full",
        "unknown_symbol",
        "invalid_date",
        "not_a_date",
        "future_start",
        "empty_symbols",
    ],
)
def test_invalid_arguments_exit_2_without_call(th: _Cli, args: list[str], message: str) -> None:
    result = th(*args)

    assert result.exit_code == 2
    assert message in result.stderr
    assert "Traceback" not in result.output
    assert th.source.calls == []
    assert not th.data.exists()


def test_full_backfill_rewrites_only_target(th: _Cli) -> None:
    th()
    others = {s: th.file(s).read_bytes() for s in ("MSFT", "SPY")}
    th.source.calls.clear()

    result = th("--symbols", "aapl", "--full", "--start", "2026-10-15")

    assert result.exit_code == 0, result.output
    assert th.source.calls == [(("AAPL",), date(2026, 10, 15), S)]
    prices = read_prices(th.file("AAPL"))
    assert prices is not None
    assert prices.bars[0][0] == date(2026, 10, 15)
    assert {s: th.file(s).read_bytes() for s in ("MSFT", "SPY")} == others
    report = RunReport.model_validate_json(run_report_path(th.data, S).read_text("utf-8"))
    assert len(report.ingest) == 2
    backfill = report.ingest[1]
    assert backfill.args.model_dump() == {
        "symbols": ["AAPL"],
        "full": True,
        "start": date(2026, 10, 15),
    }
    assert backfill.tickers[0].rewrite_reason == "backfill"


def test_benchmark_accepted_in_symbols(th: _Cli) -> None:
    result = th("--symbols", "SPY")

    assert result.exit_code == 0, result.output
    assert [call[0] for call in th.source.calls] == [("SPY",)]


def test_all_failed_exits_1(th: _Cli) -> None:
    th.source.always_fail.update({"AAPL", "MSFT", "SPY"})

    result = th()

    assert result.exit_code == 1
    report = RunReport.model_validate_json(run_report_path(th.data, S).read_text("utf-8"))
    assert {t.status for t in report.ingest[0].tickers} == {"failed"}
    assert "AAPL" in result.stdout


def test_partial_failure_exits_0(th: _Cli) -> None:
    th.source.always_fail.add("MSFT")

    result = th()

    assert result.exit_code == 0
    assert "MSFT" in result.stdout
    report = RunReport.model_validate_json(run_report_path(th.data, S).read_text("utf-8"))
    assert {t.symbol: t.status for t in report.ingest[0].tickers}["MSFT"] == "failed"


def test_unwritable_report_reported_on_stderr(th: _Cli) -> None:
    report_file = run_report_path(th.data, S)
    report_file.parent.mkdir(parents=True)
    report_file.write_bytes(b'{"schema_version": 1, "session_date": "2026-11-23"}')

    result = th()

    # Les prix sont écrits ; le rapport (autre séance) n'est pas écrasé et l'erreur est visible.
    assert read_prices(th.file("AAPL")) is not None
    assert report_file.read_bytes() == b'{"schema_version": 1, "session_date": "2026-11-23"}'
    assert "rapport" in result.stderr
    assert result.exit_code == 0


def test_invalid_config_exits_2(th: _Cli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TH_CONFIG_DIR", str(tmp_path / "missing"))

    result = th()

    assert result.exit_code == 2
    assert th.source.calls == []
