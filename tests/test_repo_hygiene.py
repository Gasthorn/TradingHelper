"""Tests d'hygiène du dépôt (F00 — R1, R4, R5, R18, R19, R20, R21)."""

from __future__ import annotations

import ast
import socket
import subprocess
from pathlib import Path

import pytest
from pytest_socket import SocketBlockedError

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
# Au-delà du minimum R19 : fichiers du dashboard.
LF_EXTENSIONS_DASHBOARD = ["js", "mjs", "cjs", "html", "css"]


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


@pytest.mark.parametrize("extension", LF_EXTENSIONS + LF_EXTENSIONS_DASHBOARD)
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


# pytest-socket émet un UserWarning à chaque tentative bloquée : ici elle est voulue.
@pytest.mark.filterwarnings("ignore:A test tried to use socket:UserWarning")
def test_network_is_blocked() -> None:
    """R4 : aucun test ne peut ouvrir de connexion réseau."""
    with pytest.raises(SocketBlockedError):
        socket.create_connection(("example.com", 80), timeout=1)


def test_research_dir_documented() -> None:
    """R5 : le dossier research/ existe et explique son rôle."""
    assert (REPO_ROOT / "research" / "README.md").is_file()


def test_src_never_imports_research() -> None:
    """R5 / P9 : le pipeline n'importe jamais le code d'exploration."""
    offenders: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            if any(m == "research" or m.startswith("research.") for m in modules):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

    assert offenders == []


def test_nvmrc_forced_lf() -> None:
    result = _git("check-attr", "eol", "--", "dashboard/.nvmrc")

    assert result.stdout.strip() == "dashboard/.nvmrc: eol: lf"


# --- Documentation (R20, R21) -------------------------------------------------------------------

DISCLAIMER_P8 = "Outil expérimental et éducatif. Ceci n'est pas un conseil en investissement."


def _readme() -> str:
    return (REPO_ROOT / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("heading", ["## Installation", "## Commandes `th`", "## Dashboard"])
def test_readme_has_section(heading: str) -> None:
    assert any(line.strip() == heading for line in _readme().splitlines()), heading


def test_readme_contains_disclaimer() -> None:
    assert DISCLAIMER_P8 in _readme()


def test_readme_documents_available_commands() -> None:
    readme = _readme()

    for command in ("uv sync", "uv run th --help", "uv run th version", "npm run build"):
        assert command in readme, command


def test_readme_mentions_dashboard_url_and_github_settings() -> None:
    readme = _readme()

    assert "github.io/TradingHelper/" in readme
    assert "active après F10" in readme
    assert "Read and write permissions" in readme  # réglage manuel exigé par F10 R7


def test_license_is_mit() -> None:
    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")

    assert license_text.splitlines()[0] == "MIT License"
    assert "Copyright (c) 2026 Gasthorn" in license_text
    assert "WITHOUT WARRANTY OF ANY KIND" in license_text
