"""Tests d'hygiène du dépôt (F00 — R1, R18, R19)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# R18 : un chemin représentatif par motif exigé (un fichier dedans pour un dossier).
IGNORED_PATHS = [
    "dashboard/public/data/overview.json",
    "dashboard/dist/index.html",
    "node_modules/pkg/index.js",
    "dashboard/node_modules/pkg/index.js",
    ".venv/pyvenv.cfg",
    "src/tradinghelper/__pycache__/cli.cpython-312.pyc",
    ".ruff_cache/CACHEDIR.TAG",
    ".mypy_cache/CACHEDIR.TAG",
    ".pytest_cache/README.md",
    ".coverage",
    "htmlcov/index.html",
    ".env",
    "research/exploration/.ipynb_checkpoints/notebook-checkpoint.ipynb",
]

# R19 : extensions dont la fin de ligne doit être LF.
LF_EXTENSIONS = ["py", "json", "yaml", "yml", "ts", "tsx", "md", "toml"]


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.parametrize("path", IGNORED_PATHS)
def test_gitignore_excludes(path: str) -> None:
    result = _git("check-ignore", "--no-index", "--quiet", path)

    assert result.returncode == 0, f"{path} n'est pas ignoré par .gitignore"


@pytest.mark.parametrize("extension", LF_EXTENSIONS)
def test_gitattributes_forces_lf(extension: str) -> None:
    result = _git("check-attr", "eol", "--", f"any/file.{extension}")

    assert result.stdout.strip() == f"any/file.{extension}: eol: lf"


def test_tracked_text_files_are_lf_in_index() -> None:
    result = _git("ls-files", "--eol")
    crlf = [line for line in result.stdout.splitlines() if line.startswith(("i/crlf", "i/mixed"))]

    assert crlf == []


def test_lockfiles_tracked() -> None:
    result = _git("ls-files", "--error-unmatch", "uv.lock", ".python-version")

    assert result.returncode == 0, result.stderr
