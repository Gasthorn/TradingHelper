"""Tests de la CLI `th` (F00 — R2, R10)."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tradinghelper.cli import app

REPO_ROOT = Path(__file__).resolve().parents[1]

runner = CliRunner()


@pytest.fixture
def invalid_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`TH_CONFIG_DIR` pointe vers un dossier sans fichiers de config."""
    config_dir = tmp_path / "nope"
    monkeypatch.setenv("TH_CONFIG_DIR", str(config_dir))
    return config_dir


@pytest.fixture
def repo_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config par défaut du dépôt, sans surcharge par variable d'environnement."""
    monkeypatch.delenv("TH_CONFIG_DIR", raising=False)


@pytest.mark.usefixtures("repo_config")
def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"tradinghelper {version('tradinghelper')}"


@pytest.mark.usefixtures("repo_config")
def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "version" in result.stdout


@pytest.mark.usefixtures("repo_config")
def test_version_from_subdirectory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT / "tests")

    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.startswith("tradinghelper ")


def test_invalid_config_exits_2_without_traceback(invalid_config_dir: Path) -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert (invalid_config_dir / "universe.yaml").as_posix() in result.stderr
    assert "introuvable" in result.stderr
    assert "Traceback" not in result.output
    assert isinstance(result.exception, SystemExit)


@pytest.mark.usefixtures("invalid_config_dir")
@pytest.mark.parametrize("args", [["--help"], ["version", "--help"]], ids=["th", "th-version"])
def test_help_works_without_valid_config(args: list[str]) -> None:
    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert "Usage" in result.stdout
