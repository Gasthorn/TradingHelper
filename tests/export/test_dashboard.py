"""Tests de l'orchestration de l'export (F08 — R1 à R3, R13, R15, R19)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from synthetic import write_synthetic_prices
from tradinghelper.config import UniverseConfig
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.export import dashboard
from tradinghelper.export.dashboard import (
    ExportOutcome,
    ExportSourceError,
    ExportTargetError,
    check_target,
    export,
    read_sources,
    replace_dir,
    resolve_git_sha,
)
from tradinghelper.schemas import HealthFile, ManifestFile, OverviewFile, TickerFile

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


# --- export() de bout en bout et git_sha (T17) --------------------------------------------------

NOW = datetime(2026, 11, 24, 22, 50, 12, 345678, tzinfo=UTC)
SHA = "430115d4c1f0e2b3a49587c6d1e0f2a3b4c5d6e7"


def _repo(tmp_path: Path, *, signals: bool = False, runs: bool = True) -> dict[str, Path]:
    """Dépôt temporaire : prix synthétiques AAPL, MSFT, SPY (+ rapports, + signaux)."""
    repo = tmp_path / "repo"
    data = repo / "data"
    _write_prices(data, "AAPL", "MSFT", "SPY")
    if runs:
        _copy_fixture_dir("runs", data)
    if signals:
        _copy_fixture_dir("signals", data)
    return {"repo": repo, "data": data, "out": repo / "dashboard" / "public" / "data"}


def _export(paths: dict[str, Path], git_sha: str | None = SHA) -> ExportOutcome:
    return export(
        _universe(),
        data_root=paths["data"],
        out=paths["out"],
        repo_root=paths["repo"],
        calendar=CAL,
        now=lambda: NOW,
        git_sha=git_sha,
    )


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_prices_only_repo_exports_m1_files(tmp_path: Path) -> None:
    """Critère M1 : prix et rapports seulement → fichiers M1, sections M3 vides (R1, R6, R13)."""
    paths = _repo(tmp_path)

    outcome = _export(paths)

    out = paths["out"]
    assert sorted(_tree(out)) == [
        "health.json", "manifest.json", "overview.json",
        "tickers/AAPL.json", "tickers/MSFT.json", "tickers/SPY.json",
    ]  # fmt: skip
    assert not (out / "portfolios").exists()
    assert not (out / "models.json").exists()
    assert outcome.out == out
    assert outcome.sizes == {name: len(content) for name, content in _tree(out).items()}
    assert outcome.data_as_of == SESSIONS[-1]

    manifest = ManifestFile.model_validate(_json(out / "manifest.json"))
    assert manifest.strategies == []
    assert [t.symbol for t in manifest.tickers] == ["AAPL", "MSFT", "SPY"]
    assert manifest.generated_at == NOW.replace(microsecond=0)
    overview = OverviewFile.model_validate(_json(out / "overview.json"))
    assert (overview.leaderboard, overview.latest_signals) == ([], [])
    for symbol in ("AAPL", "MSFT", "SPY"):
        assert TickerFile.model_validate(_json(out / "tickers" / f"{symbol}.json")).markers == []
    health = HealthFile.model_validate(_json(out / "health.json"))
    assert health.last_session == date(2026, 11, 24)
    assert [run.session_date for run in health.runs] == [date(2026, 11, 23), date(2026, 11, 20)]


def test_generated_at_is_utc_without_microseconds(tmp_path: Path) -> None:
    paths = _repo(tmp_path)

    _export(paths)

    assert _json(paths["out"] / "manifest.json")["generated_at"] == "2026-11-24T22:50:12Z"


def test_signals_fixture_markers_on_aapl(tmp_path: Path) -> None:
    """Critère M1 : marqueurs BUY et SELL d'AAPL aux bonnes dates, HOLD exclu (R9)."""
    paths = _repo(tmp_path, signals=True)

    _export(paths)

    aapl = _json(paths["out"] / "tickers" / "AAPL.json")
    assert aapl["markers"] == [
        {"date": "2026-11-20", "strategy_id": "lgbm_dir5_v3", "action": "BUY", "confidence": 0.67},
        {"date": "2026-11-23", "strategy_id": "lgbm_dir5_v3", "action": "SELL", "confidence": 0.38},
    ]
    msft = _json(paths["out"] / "tickers" / "MSFT.json")
    assert [m["strategy_id"] for m in msft["markers"]] == ["sma_cross"]


def _digests(root: Path) -> dict[str, str]:
    return {name: hashlib.sha256(content).hexdigest() for name, content in _tree(root).items()}


def test_sources_untouched(tmp_path: Path) -> None:
    """R1 : l'export ne modifie aucun fichier source."""
    paths = _repo(tmp_path, signals=True)
    before = _digests(paths["data"])

    _export(paths)

    assert _digests(paths["data"]) == before


def test_out_unchanged_when_source_invalid(tmp_path: Path) -> None:
    paths = _repo(tmp_path)
    _export(paths)
    previous = _tree(paths["out"])
    (_prices_dir(paths["data"]) / "MSFT.json").write_text("{corrompu", encoding="utf-8")

    with pytest.raises(ExportSourceError):
        _export(paths)

    assert _tree(paths["out"]) == previous


def test_dangerous_out_refused_before_reading(tmp_path: Path) -> None:
    paths = _repo(tmp_path)
    paths["out"] = paths["data"]

    with pytest.raises(ExportTargetError):
        _export(paths)


def test_two_exports_identical_bytes(tmp_path: Path) -> None:
    """R15 : mêmes sources, horloge et git_sha → mêmes octets."""
    paths = _repo(tmp_path, signals=True)
    _export(paths)
    first = _tree(paths["out"])

    _export(paths)

    assert _tree(paths["out"]) == first


def test_manifest_hashes_match_written_files(tmp_path: Path) -> None:
    paths = _repo(tmp_path)

    _export(paths)

    manifest = _json(paths["out"] / "manifest.json")
    written = _tree(paths["out"])
    assert {entry["path"] for entry in manifest["files"]} == set(written) - {"manifest.json"}
    for entry in manifest["files"]:
        content = written[entry["path"]]
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()[:16]
        assert entry["bytes"] == len(content)


def test_git_sha_from_env(tmp_path: Path) -> None:
    assert resolve_git_sha({"GITHUB_SHA": SHA.upper()}, tmp_path) == SHA


def test_git_sha_invalid_env_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    assert resolve_git_sha({"GITHUB_SHA": "pas-un-sha"}, tmp_path) is None


def test_git_sha_from_git_repo(tmp_path: Path) -> None:
    git = [
        "git",
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run([*git, "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [*git, "-C", str(tmp_path), "commit", "-q", "--allow-empty", "-m", "x"], check=True
    )
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert resolve_git_sha({}, tmp_path) == head


def test_git_sha_null_outside_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    assert resolve_git_sha({}, tmp_path) is None


def test_git_sha_null_when_git_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(dashboard.subprocess, "run", missing)

    assert resolve_git_sha({}, tmp_path) is None


# --- Taille et durée pour 20 tickers sur 15 ans (T20) -------------------------------------------

#: Tailles cibles du contrat §7 (octets) ; `tickers/` s'applique à chaque fichier.
SIZE_TARGETS = {
    "manifest.json": 10 * 1024,
    "overview.json": 100 * 1024,
    "health.json": 20 * 1024,
    "tickers/": 500 * 1024,
}
MAX_EXPORT_SECONDS = 30.0


def _target_for(path: str) -> int:
    return SIZE_TARGETS["tickers/"] if path.startswith("tickers/") else SIZE_TARGETS[path]


def test_20_tickers_15_years_sizes_and_duration(tmp_path: Path) -> None:
    """R19 : 20 tickers + SPY sur ≈ 3 780 séances, prix à 4 décimales (pire cas) : chaque
    fichier sous sa taille cible et export en moins de 30 s."""
    symbols = [f"T{i:02d}" for i in range(20)]
    universe = UniverseConfig.model_validate(
        {
            "currency": "USD",
            "benchmark": "SPY",
            "tickers": [
                {
                    "symbol": s,
                    "name": f"Société {s}",
                    "sector": "Industrials",
                    "start": "2011-01-01",
                }
                for s in symbols
            ],
        }
    )
    data = tmp_path / "repo" / "data"
    sessions = CAL.sessions(date(2011, 11, 25), date(2026, 11, 23))
    write_synthetic_prices(
        _prices_dir(data), [*symbols, "SPY"], sessions, np.random.default_rng(15)
    )
    _copy_fixture_dir("runs", data)
    _copy_fixture_dir("signals", data)
    out = tmp_path / "repo" / "dashboard" / "public" / "data"

    started = time.perf_counter()
    outcome = export(
        universe,
        data_root=data,
        out=out,
        repo_root=tmp_path / "repo",
        calendar=CAL,
        now=lambda: NOW,
        git_sha=SHA,
    )
    elapsed = time.perf_counter() - started

    assert len(sessions) > 3_700
    assert len(outcome.sizes) == 21 + 3
    over = {path: size for path, size in outcome.sizes.items() if size >= _target_for(path)}
    assert over == {}, f"tailles cibles dépassées : {over}"
    assert elapsed < MAX_EXPORT_SECONDS, f"{elapsed:.1f} s"
