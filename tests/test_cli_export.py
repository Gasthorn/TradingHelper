"""Tests de la commande `th export` (F08 — R1, R3, R11).

`CliRunner` dans un dépôt temporaire (`pyproject.toml`), config temporaire (`TH_CONFIG_DIR`),
horloge et `git_sha` remplacés. Aucun réseau.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from typer.testing import CliRunner, Result

from fakes import FakeClock
from synthetic import write_synthetic_prices
from tradinghelper import cli
from tradinghelper.data.calendar import NyseCalendar

from conftest import WriteConfig

CAL = NyseCalendar()
NOW = datetime(2026, 11, 24, 22, 50, 12, tzinfo=UTC)
SHA = "430115d4c1f0e2b3a49587c6d1e0f2a3b4c5d6e7"
SESSIONS = CAL.sessions(date(2026, 10, 1), date(2026, 11, 23))
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "export"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

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
    repo: Path
    data: Path
    runner: CliRunner

    @property
    def default_out(self) -> Path:
        return self.repo / "dashboard" / "public" / "data"

    def __call__(self, *args: str) -> Result:
        return self.runner.invoke(cli.app, ["export", *args])

    def prices_dir(self) -> Path:
        return self.data / "raw" / "prices"


@pytest.fixture
def th(tmp_path: Path, write_config: WriteConfig, monkeypatch: pytest.MonkeyPatch) -> _Cli:
    """Dépôt temporaire avec données par défaut (`<repo>/data`) : AAPL, MSFT, SPY + rapports."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'tmp'\n", encoding="utf-8")
    data = repo / "data"
    write_synthetic_prices(data / "raw" / "prices", ["AAPL", "MSFT", "SPY"], SESSIONS,
                           np.random.default_rng(1))  # fmt: skip
    shutil.copytree(FIXTURES / "runs", data / "runs")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("TH_CONFIG_DIR", str(write_config(universe=UNIVERSE)))
    monkeypatch.delenv("TH_DATA_DIR", raising=False)
    monkeypatch.setattr(cli, "_now", FakeClock(NOW))
    monkeypatch.setattr(cli, "_git_sha", lambda: SHA)
    return _Cli(repo, data, CliRunner())


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_help_lists_export(th: _Cli) -> None:
    result = th.runner.invoke(cli.app, ["export", "--help"])

    text = ANSI_ESCAPE.sub("", result.stdout)
    assert result.exit_code == 0
    assert "--out" in text
    assert "dashboard/public/data" in text
    assert "Code 1" in text


def test_exports_to_default_out(th: _Cli) -> None:
    result = th()

    assert result.exit_code == 0, result.output
    assert sorted(_tree(th.default_out)) == [
        "health.json", "manifest.json", "overview.json",
        "tickers/AAPL.json", "tickers/MSFT.json", "tickers/SPY.json",
    ]  # fmt: skip


def test_custom_out_and_data_dir(th: _Cli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    other_data = tmp_path / "elsewhere"
    write_synthetic_prices(other_data / "raw" / "prices", ["AAPL"], SESSIONS,
                           np.random.default_rng(2))  # fmt: skip
    monkeypatch.setenv("TH_DATA_DIR", str(other_data))
    out = tmp_path / "export"

    result = th("--out", str(out))

    assert result.exit_code == 0, result.output
    assert sorted(_tree(out)) == [
        "health.json",
        "manifest.json",
        "overview.json",
        "tickers/AAPL.json",
    ]
    assert not th.default_out.exists()


def test_summary_on_stdout(th: _Cli) -> None:
    result = th()

    sizes = {name: len(content) for name, content in _tree(th.default_out).items()}
    biggest = max(sizes, key=lambda name: sizes[name])
    assert result.exit_code == 0
    assert "6 fichier(s)" in result.stdout
    assert biggest in result.stdout
    assert "2026-11-23" in result.stdout  # data_as_of
    assert result.stderr == ""


def test_summary_without_prices(th: _Cli) -> None:
    shutil.rmtree(th.prices_dir())

    result = th()

    assert result.exit_code == 0, result.output
    assert "aucune donnée de prix" in result.stdout
    assert sorted(_tree(th.default_out)) == ["health.json", "manifest.json", "overview.json"]


def test_corrupted_price_file_exits_1_and_names_file(th: _Cli) -> None:
    th()
    previous = _tree(th.default_out)
    (th.prices_dir() / "MSFT.json").write_text("{corrompu", encoding="utf-8")

    result = th()

    assert result.exit_code == 1
    assert "MSFT.json" in result.stderr
    assert "Traceback" not in result.output
    assert _tree(th.default_out) == previous  # rien n'est écrit (R3)


def test_all_bad_sources_listed(th: _Cli) -> None:
    (th.prices_dir() / "MSFT.json").write_text("{corrompu", encoding="utf-8")
    (th.data / "runs" / "2026-11-23.json").write_text('{"schema_version": 2}', encoding="utf-8")

    result = th()

    assert result.exit_code == 1
    assert "MSFT.json" in result.stderr
    assert "2026-11-23.json" in result.stderr
    assert "2 source(s) invalide(s)" in result.stderr
    assert not th.default_out.exists()


@pytest.mark.parametrize("target", ["data", ".", "config"])
def test_dangerous_out_exits_2(th: _Cli, target: str) -> None:
    (th.repo / "config").mkdir(exist_ok=True)
    (th.repo / "config" / "notes.txt").write_text("à garder", encoding="utf-8")
    before = _tree(th.repo)

    result = th("--out", target)

    assert result.exit_code == 2
    assert "Erreur" in result.stderr
    assert "Traceback" not in result.output
    assert _tree(th.repo) == before


def test_config_error_exits_2(th: _Cli, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TH_CONFIG_DIR", str(tmp_path / "absent"))

    result = th()

    assert result.exit_code == 2
    assert "configuration" in result.stderr
    assert not th.default_out.exists()


def test_generated_at_uses_injected_clock(th: _Cli) -> None:
    th()

    manifest = _json(th.default_out / "manifest.json")
    assert manifest["generated_at"] == "2026-11-24T22:50:12Z"
    assert _json(th.default_out / "health.json")["last_session"] == "2026-11-24"


def test_git_sha_injected(th: _Cli) -> None:
    th()

    assert _json(th.default_out / "manifest.json")["git_sha"] == SHA


def test_git_sha_null_is_accepted(th: _Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_git_sha", lambda: None)

    result = th()

    assert result.exit_code == 0, result.output
    assert _json(th.default_out / "manifest.json")["git_sha"] is None
