"""Tests de la commande `th commit-message` (F10 R5).

Rapports écrits sous `TH_DATA_DIR`, horloge remplacée, aucune config requise. Aucun réseau.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from fakes import FakeClock
from tradinghelper import cli
from tradinghelper.data.storage import run_report_path, update_run_report
from tradinghelper.schemas import IngestArgs, IngestRun, IngestTickerResult

NOW = datetime(2026, 11, 24, 22, 45, tzinfo=UTC)  # S = 2026-11-24
SESSION = date(2026, 11, 24)
T0 = "2026-11-24T22:30:00Z"

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _run(started_at: datetime, symbol: str, *, rewritten: bool) -> IngestRun:
    return IngestRun(
        started_at=started_at,
        finished_at=started_at,
        duration_s=1.0,
        args=IngestArgs(symbols=None, full=False, start=None),
        exit_code=0,
        tickers=[
            IngestTickerResult(
                symbol=symbol,
                status="ok",
                mode="full" if rewritten else "incremental",
                bars_added=1,
                bars_revised=0,
                history_rewritten=rewritten,
                rewrite_reason="revision" if rewritten else None,
                attempts=1,
                error=None,
            )
        ],
        warnings=[],
    )


@pytest.fixture
def data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    monkeypatch.setenv("TH_DATA_DIR", str(root))
    monkeypatch.setenv("TH_CONFIG_DIR", str(tmp_path / "pas-de-config"))  # config non requise
    monkeypatch.setattr(cli, "_now", FakeClock(NOW))
    return root


def _invoke(*args: str) -> Result:
    return CliRunner().invoke(cli.app, ["commit-message", *args])


def test_prints_message_from_reports(data: Path) -> None:
    started = datetime(2026, 11, 24, 22, 31, 2, tzinfo=UTC)
    update_run_report(
        run_report_path(data, SESSION), SESSION, _run(started, "AAPL", rewritten=True)
    )

    result = _invoke("--kind", "daily", "--since", T0)

    assert result.exit_code == 0, result.output
    assert result.stdout == "data: daily update 2026-11-24 (history rewrite: AAPL)\n"


def test_no_runs_dir_uses_current_session(data: Path) -> None:
    result = _invoke("--kind", "backfill", "--since", T0)

    assert result.exit_code == 0, result.output
    assert result.stdout == "data: backfill 2026-11-24\n"


def test_since_with_offset_is_converted_to_utc(data: Path) -> None:
    started = datetime(2026, 11, 24, 22, 31, 2, tzinfo=UTC)
    update_run_report(
        run_report_path(data, SESSION), SESSION, _run(started, "AAPL", rewritten=True)
    )

    # 23:00+01:00 = 22:00Z : l'entrée de 22:31Z est retenue.
    result = _invoke("--kind", "daily", "--since", "2026-11-24T23:00:00+01:00")

    assert result.stdout == "data: daily update 2026-11-24 (history rewrite: AAPL)\n"


def test_invalid_report_exits_1(data: Path) -> None:
    bad = run_report_path(data, SESSION)
    bad.parent.mkdir(parents=True)
    bad.write_text("{ pas du json", encoding="utf-8")

    result = _invoke("--kind", "daily", "--since", T0)

    assert result.exit_code == 1
    assert "2026-11-24.json" in result.stderr
    assert result.stdout == ""
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "since", ["2026-11-24T22:30:00", "hier", ""], ids=["sans-fuseau", "mal-forme", "vide"]
)
def test_invalid_since_exits_2(data: Path, since: str) -> None:
    result = _invoke("--kind", "daily", "--since", since)

    assert result.exit_code == 2
    assert "--since" in result.stderr
    assert result.stdout == ""


def test_unknown_kind_exits_2(data: Path) -> None:
    result = _invoke("--kind", "weekly", "--since", T0)

    assert result.exit_code == 2
    assert "--kind" in result.stderr
    assert result.stdout == ""


def test_runs_without_config(data: Path) -> None:
    """`TH_CONFIG_DIR` pointe vers un dossier absent (fixture) : la commande réussit quand même."""
    result = _invoke("--kind", "model", "--since", T0)

    assert result.exit_code == 0, result.output
    assert result.stdout == "model: weekly training 2026-11-24\n"


def test_help_lists_options() -> None:
    result = CliRunner().invoke(cli.app, ["commit-message", "--help"])

    text = ANSI_ESCAPE.sub("", result.stdout)
    assert result.exit_code == 0
    assert "--kind" in text
    assert "--since" in text
