"""Tests de la CLI `th` (F00 — R2)."""

from __future__ import annotations

from importlib.metadata import version

from typer.testing import CliRunner

from tradinghelper.cli import app

runner = CliRunner()


def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"tradinghelper {version('tradinghelper')}"


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "version" in result.stdout
