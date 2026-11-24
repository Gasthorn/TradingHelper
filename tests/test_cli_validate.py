"""Tests de la commande `th validate` (F02 — R5, R6, R7).

`CliRunner` avec une config temporaire (`TH_CONFIG_DIR`), un dossier de données temporaire
(`TH_DATA_DIR`) et l'horloge remplacée. Aucun réseau.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from fakes import FakeClock
from tradinghelper import cli
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.storage import dumps_prices, prices_dir, prices_path, run_report_path
from tradinghelper.schemas import PRICE_COLUMNS, Bar, PricesFile, RunReport

from conftest import WriteConfig

CAL = NyseCalendar()
NOW = datetime(2026, 11, 24, 22, 30, tzinfo=UTC)  # S = 2026-11-24
S = date(2026, 11, 24)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "validate"
CORRUPTED = FIXTURES / "duplicate_and_high_lt_low.json"
JUMP = FIXTURES / "jump_plus_60.json"

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

UNIVERSE = {
    "currency": "USD",
    "benchmark": "SPY",
    "tickers": [
        {"symbol": "AAPL", "name": "Apple", "sector": "Tech", "start": date(2026, 10, 1)},
        {"symbol": "MSFT", "name": "Microsoft", "sector": "Tech", "start": date(2026, 10, 1)},
    ],
}


def _fresh_bars(start: date = date(2026, 11, 2), end: date = S) -> list[Bar]:
    return [(d, 100.0, 101.0, 99.0, 100.0, 98.0, 1_000_000) for d in CAL.sessions(start, end)]


@dataclass
class _Cli:
    data: Path
    clock: FakeClock
    runner: CliRunner

    def __call__(self, *args: str) -> Result:
        return self.runner.invoke(cli.app, ["validate", *args])

    def put_fixture(self, symbol: str, fixture: Path) -> Path:
        target = prices_path(self.data, symbol)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixture, target)
        return target

    def put_bars(self, symbol: str, bars: list[Bar]) -> Path:
        target = prices_path(self.data, symbol)
        target.parent.mkdir(parents=True, exist_ok=True)
        prices = PricesFile(
            schema_version=1,
            symbol=symbol,
            currency="USD",
            source="yfinance",
            columns=PRICE_COLUMNS,
            last_updated=NOW,
            bars=bars,
        )
        target.write_text(dumps_prices(prices), encoding="utf-8")
        return target


@pytest.fixture
def th(tmp_path: Path, write_config: WriteConfig, monkeypatch: pytest.MonkeyPatch) -> _Cli:
    config_dir = write_config(universe=UNIVERSE)
    data = tmp_path / "data"
    monkeypatch.setenv("TH_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("TH_DATA_DIR", str(data))
    env = _Cli(data, FakeClock(NOW), CliRunner())
    monkeypatch.setattr(cli, "_now", env.clock)
    return env


def _fresh_universe(th: _Cli, *symbols: str) -> None:
    for symbol in symbols:
        th.put_bars(symbol, _fresh_bars())


# --- Arguments et codes de sortie (R5, R6) ------------------------------------------------------


def test_validate_listed_in_help(th: _Cli) -> None:
    result = th.runner.invoke(cli.app, ["validate", "--help"])

    # Sur GitHub Actions (et avec FORCE_COLOR), rich colore l'aide : les codes ANSI coupent
    # `--symbols` en plusieurs segments. On compare le texte sans mise en forme.
    text = ANSI_ESCAPE.sub("", result.stdout)
    assert result.exit_code == 0
    assert "--symbols" in text
    assert "--all-history" in text


@pytest.mark.parametrize(
    ("args", "message"),
    [(["--symbols", "AAPL,XOM"], "XOM"), (["--symbols", " , "], "--symbols")],
    ids=["unknown_symbol", "empty_symbols"],
)
def test_unknown_symbol_exits_2(th: _Cli, args: list[str], message: str) -> None:
    _fresh_universe(th, "AAPL", "MSFT", "SPY")

    result = th(*args)

    assert result.exit_code == 2
    assert message in result.stderr
    assert "Traceback" not in result.output


def test_config_error_exits_2(th: _Cli, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TH_CONFIG_DIR", str(tmp_path / "absent"))

    result = th()

    assert result.exit_code == 2
    assert "configuration" in result.stderr


def test_clean_data_exits_0(th: _Cli) -> None:
    _fresh_universe(th, "AAPL", "MSFT", "SPY")

    result = th()

    assert result.exit_code == 0, result.output
    assert result.stderr == ""


def test_corrupted_fixture_exits_1_with_ticker_and_date(th: _Cli) -> None:
    """Critère d'acceptation : date dupliquée et `high < low` → code 1, ticker + date."""
    _fresh_universe(th, "MSFT", "SPY")
    th.put_fixture("AAPL", CORRUPTED)

    result = th()

    assert result.exit_code == 1
    lines = result.stderr.splitlines()
    assert any(line.startswith("AAPL 2026-11-20 dates_not_increasing: ") for line in lines)
    assert any(line.startswith("AAPL 2026-11-23 ohlc_inconsistent: ") for line in lines)
    assert "Traceback" not in result.output


def test_undated_violation_line(th: _Cli) -> None:
    _fresh_universe(th, "AAPL", "MSFT", "SPY")
    (prices_dir(th.data) / "readme.json").write_text("{tronqu", encoding="utf-8")

    result = th()

    assert result.exit_code == 1
    assert any(line.startswith("readme - unreadable: ") for line in result.stderr.splitlines())


def test_jump_fixture_warns_exit_0(th: _Cli) -> None:
    """Critère d'acceptation : saut de +60 % → avertissement, code 0."""
    _fresh_universe(th, "MSFT", "SPY")
    th.put_fixture("AAPL", JUMP)

    result = th()

    assert result.exit_code == 0, result.output
    assert "large_move" in result.stdout
    assert result.stderr == ""


def test_summary_on_stdout(th: _Cli) -> None:
    _fresh_universe(th, "MSFT")
    th.put_fixture("AAPL", CORRUPTED)

    result = th()

    assert "Séance 2026-11-24" in result.stdout
    assert "2 fichier(s) vérifié(s)" in result.stdout
    assert "2 violation(s)" in result.stdout
    assert "missing_file: 1" in result.stdout


def test_all_history_flag(th: _Cli) -> None:
    _fresh_universe(th, "MSFT", "SPY")
    jump = date(2026, 10, 6)
    th.put_bars(
        "AAPL",
        [
            (d, c, round(c * 1.01, 4), round(c * 0.99, 4), c, c, 1000)
            for d in CAL.sessions(date(2026, 10, 1), S)
            for c in [160.0 if d >= jump else 100.0]
        ],
    )

    assert "large_move" not in th().stdout
    assert "large_move: 1" in th("--all-history").stdout


def test_symbols_restricts_validation(th: _Cli) -> None:
    th.put_fixture("AAPL", JUMP)
    th.put_fixture("MSFT", CORRUPTED)  # `symbol` incohérent, mais non listé

    result = th("--symbols", "aapl")

    assert result.exit_code == 0, result.output
    assert "1 fichier(s) vérifié(s)" in result.stdout


# --- Écriture conditionnelle du rapport (R7) ---------------------------------------------------


def _report_file(th: _Cli, session: date = S) -> Path:
    return run_report_path(th.data, session)


def _ingest_report(th: _Cli) -> dict[str, Any]:
    report = {
        "schema_version": 1,
        "session_date": S.isoformat(),
        "ingest": [
            {
                "started_at": "2026-11-24T22:31:02Z",
                "finished_at": "2026-11-24T22:32:10Z",
                "duration_s": 68.0,
                "args": {"symbols": None, "full": False, "start": None},
                "exit_code": 0,
                "tickers": [],
                "warnings": [],
            }
        ],
    }
    target = _report_file(th)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def test_appends_to_existing_report_keeps_ingest(th: _Cli) -> None:
    _fresh_universe(th, "MSFT", "SPY")
    th.put_fixture("AAPL", JUMP)
    existing = _ingest_report(th)

    result = th()

    assert result.exit_code == 0, result.output
    data = json.loads(_report_file(th).read_text(encoding="utf-8"))
    assert data["ingest"] == existing["ingest"]
    (entry,) = data["validate"]
    assert entry["exit_code"] == 0
    assert [w["rule"] for w in entry["warnings"]] == ["large_move"]
    assert _report_file(th).name in result.stdout


def test_no_report_written_on_holiday_without_violation(th: _Cli) -> None:
    """Thanksgiving, aucun rapport du jour, aucune violation : aucun fichier écrit."""
    _fresh_universe(th, "AAPL", "MSFT", "SPY")
    th.clock.now = datetime(2026, 11, 26, 22, 30, tzinfo=UTC)  # S = 2026-11-25

    result = th()

    assert result.exit_code == 0, result.output
    assert not (th.data / "runs").exists()
    assert "aucun rapport écrit" in result.stdout


def test_report_written_with_exit_code_1(th: _Cli) -> None:
    _fresh_universe(th, "MSFT", "SPY")
    th.put_fixture("AAPL", CORRUPTED)

    result = th()

    assert result.exit_code == 1
    report = RunReport.model_validate_json(_report_file(th).read_text(encoding="utf-8"))
    (entry,) = report.validate_
    assert entry.exit_code == 1
    assert {v.rule for v in entry.violations} == {"dates_not_increasing", "ohlc_inconsistent"}
    assert report.ingest == []
    assert "ingest" not in json.loads(_report_file(th).read_text(encoding="utf-8"))


def test_report_named_after_session(th: _Cli) -> None:
    """Run à 00:30 UTC le 25/11 : la dernière séance clôturée reste le 24/11."""
    _fresh_universe(th, "MSFT", "SPY")
    th.put_fixture("AAPL", CORRUPTED)
    th.clock.now = datetime(2026, 11, 25, 0, 30, tzinfo=UTC)

    th()

    assert [p.name for p in (th.data / "runs").iterdir()] == ["2026-11-24.json"]


@pytest.mark.parametrize(
    "content",
    [b"{tronqu", b'{"schema_version": 1, "session_date": "2026-11-23"}'],
    ids=["JSON invalide", "autre séance"],
)
def test_unreadable_report_not_overwritten(th: _Cli, content: bytes) -> None:
    _fresh_universe(th, "MSFT", "SPY")
    th.put_fixture("AAPL", CORRUPTED)
    target = _report_file(th)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    result = th()

    assert result.exit_code == 1  # code de la validation, inchangé (décision 3 du plan)
    assert target.read_bytes() == content
    assert "rapport de run non écrit" in result.stderr
    assert "Traceback" not in result.output


def test_unreadable_report_keeps_exit_0_without_violation(th: _Cli) -> None:
    _fresh_universe(th, "AAPL", "MSFT", "SPY")
    target = _report_file(th)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"{tronqu")

    result = th()

    assert result.exit_code == 0
    assert target.read_bytes() == b"{tronqu"
    assert "rapport de run non écrit" in result.stderr


def test_report_matches_json_schema(th: _Cli) -> None:
    _fresh_universe(th, "MSFT", "SPY")
    th.put_fixture("AAPL", CORRUPTED)
    _ingest_report(th)

    th()
    th("--all-history")

    data = json.loads(_report_file(th).read_text(encoding="utf-8"))
    report = RunReport.model_validate(data)
    assert len(report.validate_) == 2
    assert report.validate_[1].args.all_history is True
    assert "validate_" not in data
