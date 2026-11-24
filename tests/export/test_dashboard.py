"""Tests de l'orchestration de l'export (F08 — R1 à R3, R13, R15, R19)."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from synthetic import write_synthetic_prices
from tradinghelper.config import UniverseConfig
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.export.dashboard import ExportSourceError, read_sources

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "export"
CAL = NyseCalendar()
SESSIONS = CAL.sessions(date(2026, 10, 1), date(2026, 11, 23))


def _universe() -> UniverseConfig:
    return UniverseConfig.model_validate(
        {
            "currency": "USD",
            "benchmark": "SPY",
            "tickers": [
                {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Tech", "start": "2010-01-01"},
                {"symbol": "MSFT", "name": "Microsoft", "sector": "Tech", "start": "2010-01-01"},
            ],
        }
    )


def _prices_dir(root: Path) -> Path:
    return root / "raw" / "prices"


def _write_prices(root: Path, *symbols: str, seed: int = 1) -> None:
    write_synthetic_prices(_prices_dir(root), list(symbols), SESSIONS, np.random.default_rng(seed))


def _copy_fixture_dir(name: str, root: Path) -> Path:
    target = root / name
    shutil.copytree(FIXTURES / name, target)
    return target


def _report_json(day: date) -> str:
    return json.dumps({"schema_version": 1, "session_date": day.isoformat()})


# --- Lecture des sources (T15) -----------------------------------------------------------------


def test_read_sources_prices_only(tmp_path: Path) -> None:
    """Dépôt M1 sans `runs/` ni `signals/` : listes vides (R13)."""
    _write_prices(tmp_path, "SPY", "MSFT", "AAPL")

    sources = read_sources(_universe(), tmp_path)

    assert list(sources.prices) == ["AAPL", "MSFT", "SPY"]  # ordre des cibles
    assert sources.prices["AAPL"].symbol == "AAPL"
    assert sources.reports == []
    assert sources.signals == []


def test_read_sources_empty_data_root(tmp_path: Path) -> None:
    sources = read_sources(_universe(), tmp_path / "absent")

    assert (sources.prices, sources.reports, sources.signals) == ({}, [], [])


def test_missing_universe_file_skipped(tmp_path: Path) -> None:
    _write_prices(tmp_path, "AAPL", "SPY")

    assert list(read_sources(_universe(), tmp_path).prices) == ["AAPL", "SPY"]


def test_orphan_price_file_not_read(tmp_path: Path) -> None:
    """Un fichier hors univers n'est pas exporté, même corrompu (Définitions)."""
    _write_prices(tmp_path, "AAPL", "TSLA")
    (_prices_dir(tmp_path) / "OLD.json").write_text("{corrompu", encoding="utf-8")

    assert list(read_sources(_universe(), tmp_path).prices) == ["AAPL"]


def test_latest_json_not_read_as_dated_signals(tmp_path: Path) -> None:
    _copy_fixture_dir("signals", tmp_path)

    signals = read_sources(_universe(), tmp_path).signals

    assert [s.date for s in signals] == [date(2026, 11, 19), date(2026, 11, 20), date(2026, 11, 23)]


def test_reports_read_most_recent_first(tmp_path: Path) -> None:
    _copy_fixture_dir("runs", tmp_path)

    reports = read_sources(_universe(), tmp_path).reports

    assert [r.session_date for r in reports] == [date(2026, 11, 23), date(2026, 11, 20)]


@pytest.mark.parametrize(
    "name", ["notes.json", "2026-11-23.json.bak", ".2026-11-23.json.abc.tmp", "2026-13-45.json"]
)
def test_non_matching_filenames_ignored(tmp_path: Path, name: str) -> None:
    for folder in ("runs", "signals"):
        directory = _copy_fixture_dir(folder, tmp_path)
        (directory / name).write_text("{pas du json", encoding="utf-8")

    sources = read_sources(_universe(), tmp_path)

    assert len(sources.reports) == 2
    assert len(sources.signals) == 3


def test_only_10_most_recent_reports_read(tmp_path: Path) -> None:
    """Un 11e rapport, plus ancien et corrompu, est ignoré (décision 4 du plan)."""
    runs = tmp_path / "runs"
    runs.mkdir()
    days = [CAL.shift(date(2026, 11, 23), -i) for i in range(11)]
    for day in days[:10]:
        (runs / f"{day.isoformat()}.json").write_text(_report_json(day), encoding="utf-8")
    (runs / f"{days[10].isoformat()}.json").write_text("{corrompu", encoding="utf-8")

    reports = read_sources(_universe(), tmp_path).reports

    assert [r.session_date for r in reports] == days[:10]


def test_empty_bars_price_file_is_a_problem(tmp_path: Path) -> None:
    """Un fichier sans barre ne peut pas être exporté : source invalide (règle F02 `empty_bars`)."""
    write_synthetic_prices(_prices_dir(tmp_path), ["AAPL"], [], np.random.default_rng(0))

    with pytest.raises(ExportSourceError) as excinfo:
        read_sources(_universe(), tmp_path)

    (problem,) = excinfo.value.problems
    assert problem.path == _prices_dir(tmp_path) / "AAPL.json"
    assert "aucune barre" in problem.reason


def test_report_session_must_match_filename(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "2026-11-23.json").write_text(_report_json(date(2026, 11, 20)), encoding="utf-8")

    with pytest.raises(ExportSourceError, match="2026-11-20"):
        read_sources(_universe(), tmp_path)


def test_signals_date_must_match_filename(tmp_path: Path) -> None:
    signals = _copy_fixture_dir("signals", tmp_path)
    shutil.copy(signals / "2026-11-20.json", signals / "2026-11-24.json")

    with pytest.raises(ExportSourceError, match="2026-11-24"):
        read_sources(_universe(), tmp_path)


def test_invalid_sources_all_listed(tmp_path: Path) -> None:
    """Prix corrompu + signal invalide + rapport récent invalide → une seule erreur, 3 problèmes."""
    _write_prices(tmp_path, "AAPL", "SPY")
    (_prices_dir(tmp_path) / "MSFT.json").write_text("{corrompu", encoding="utf-8")
    signals = _copy_fixture_dir("signals", tmp_path)
    (signals / "2026-11-20.json").write_text('{"schema_version": 1}', encoding="utf-8")
    runs = _copy_fixture_dir("runs", tmp_path)
    (runs / "2026-11-23.json").write_text('{"schema_version": 2}', encoding="utf-8")

    with pytest.raises(ExportSourceError) as excinfo:
        read_sources(_universe(), tmp_path)

    paths = [problem.path for problem in excinfo.value.problems]
    assert paths == [
        _prices_dir(tmp_path) / "MSFT.json",
        runs / "2026-11-23.json",
        signals / "2026-11-20.json",
    ]
    assert all(problem.reason for problem in excinfo.value.problems)
    assert "MSFT.json" in str(excinfo.value)
