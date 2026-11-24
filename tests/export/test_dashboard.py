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
from tradinghelper.export import dashboard
from tradinghelper.export.dashboard import (
    ExportSourceError,
    ExportTargetError,
    check_target,
    read_sources,
    replace_dir,
)

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


# --- Garde-fou sur `--out` et remplacement du dossier (T16) -------------------------------------


@pytest.fixture
def layout(tmp_path: Path) -> dict[str, Path]:
    """Arborescence type : dépôt contenant `data/` et `dashboard/public/data/`."""
    repo = tmp_path / "repo"
    data = repo / "data"
    (data / "raw" / "prices").mkdir(parents=True)
    (repo / "dashboard" / "public").mkdir(parents=True)
    return {"repo": repo, "data": data, "out": repo / "dashboard" / "public" / "data"}


def _check(out: Path, layout: dict[str, Path]) -> None:
    check_target(out, data_root=layout["data"], repo_root=layout["repo"])


@pytest.mark.parametrize(
    "target",
    ["repo_root", "parent_of_repo", "data_root", "inside_data_root", "parent_of_data_root",
     "non_empty_without_manifest", "existing_file"],
)  # fmt: skip
def test_check_target_refuses(layout: dict[str, Path], target: str) -> None:
    """Décision 2 du plan : jamais de suppression d'un dossier qui n'est pas un export."""
    repo, data = layout["repo"], layout["data"]
    other = repo / "other"
    other.mkdir()
    (other / "notes.txt").write_text("à garder", encoding="utf-8")
    (repo / "file.json").write_text("{}", encoding="utf-8")
    out = {
        "repo_root": repo,
        "parent_of_repo": repo.parent,
        "data_root": data,
        "inside_data_root": data / "raw",
        "parent_of_data_root": data.parent,
        "non_empty_without_manifest": other,
        "existing_file": repo / "file.json",
    }[target]

    with pytest.raises(ExportTargetError):
        _check(out, layout)


def test_check_target_refuses_relative_alias_of_repo(
    layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(layout["repo"] / "dashboard")

    with pytest.raises(ExportTargetError):
        _check(Path(".."), layout)


@pytest.mark.parametrize("state", ["missing_dir", "empty_dir", "previous_export"])
def test_check_target_accepts(layout: dict[str, Path], state: str) -> None:
    out = layout["out"]
    if state != "missing_dir":
        out.mkdir()
    if state == "previous_export":
        (out / "manifest.json").write_text("{}", encoding="utf-8")
        (out / "tickers").mkdir()

    _check(out, layout)


FILES = {
    "manifest.json": b'{"m":1}',
    "overview.json": b'{"o":1}',
    "tickers/AAPL.json": b'{"t":"AAPL"}',
    "tickers/BRK.B.json": b'{"t":"BRK.B"}',
}


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _siblings(out: Path) -> list[str]:
    return sorted(path.name for path in out.parent.iterdir())


def test_replace_dir_creates_parent_and_subdirs(tmp_path: Path) -> None:
    out = tmp_path / "a" / "b" / "data"

    replace_dir(out, FILES)

    assert _tree(out) == FILES
    assert _siblings(out) == ["data"]  # aucun dossier temporaire restant


def test_replace_dir_removes_stale_files(tmp_path: Path) -> None:
    """R2 : aucun fichier d'un export précédent ne subsiste."""
    out = tmp_path / "data"
    replace_dir(out, {**FILES, "tickers/OLD.json": b"{}", "obsolete.json": b"{}"})

    replace_dir(out, FILES)

    assert _tree(out) == FILES
    assert _siblings(out) == ["data"]


def test_failure_during_write_keeps_previous_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "data"
    replace_dir(out, {"manifest.json": b"ancien"})
    calls = {"n": 0}
    original = dashboard._write_file

    def failing(path: Path, content: bytes) -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disque plein")
        original(path, content)

    monkeypatch.setattr(dashboard, "_write_file", failing)

    with pytest.raises(OSError, match="disque plein"):
        replace_dir(out, FILES)

    assert _tree(out) == {"manifest.json": b"ancien"}
    assert _siblings(out) == ["data"]


def test_no_temp_dir_left_after_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "data"

    def failing(path: Path, content: bytes) -> None:
        raise OSError("refusé")

    monkeypatch.setattr(dashboard, "_write_file", failing)

    with pytest.raises(OSError, match="refusé"):
        replace_dir(out, FILES)

    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_failure_after_move_restores_previous_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le renommage final échoue alors que l'ancien export a déjà été déplacé : il est restauré."""
    out = tmp_path / "data"
    replace_dir(out, {"manifest.json": b"ancien"})
    original = dashboard._move
    calls = {"n": 0}

    def failing(src: Path, dst: Path) -> None:
        calls["n"] += 1
        if calls["n"] == 2:  # 1 : ancien → sauvegarde ; 2 : temporaire → out
            raise PermissionError("dossier ouvert ailleurs")
        original(src, dst)

    monkeypatch.setattr(dashboard, "_move", failing)

    with pytest.raises(PermissionError):
        replace_dir(out, FILES)

    assert _tree(out) == {"manifest.json": b"ancien"}
    assert _siblings(out) == ["data"]
