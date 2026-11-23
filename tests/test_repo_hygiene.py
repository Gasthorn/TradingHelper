"""Tests d'hygiène du dépôt (F00 — R1, R4, R5, R15 à R21)."""

from __future__ import annotations

import ast
import importlib
import re
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
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


def _imports_of(root: Path, package: str) -> list[str]:
    """Emplacements `fichier:ligne` sous `root` qui importent `package` (ou un sous-module)."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # Import relatif (`from . import x`) : jamais un paquet tiers.
                modules = [node.module or ""] if node.level == 0 else []
            else:
                continue
            if any(m == package or m.startswith(f"{package}.") for m in modules):
                found.append(f"{path.relative_to(root).as_posix()}:{node.lineno}")
    return found


def test_src_never_imports_research() -> None:
    """R5 / P9 : le pipeline n'importe jamais le code d'exploration."""
    assert _imports_of(REPO_ROOT / "src", "research") == []


# F01 (plan) : chaque paquet tiers lié à la source est confiné à un seul module.
PROVIDER_MODULES = {
    "yfinance": "tradinghelper/data/source.py",
    "pandas": "tradinghelper/data/source.py",
    "pandas_market_calendars": "tradinghelper/data/calendar.py",
}


@pytest.mark.parametrize("package", sorted(PROVIDER_MODULES))
# À l'import, urllib3 (tiré par yfinance) sonde IPv6 en créant une socket locale sur `::1`, sans
# réseau, et ignore l'échec : pytest-socket la bloque et émet ce UserWarning, sans conséquence.
@pytest.mark.filterwarnings("ignore:A test tried to use socket:UserWarning")
def test_provider_packages_importable(package: str) -> None:
    """F01 R5, R16 : dépendances déclarées et importables sans réseau."""
    importlib.import_module(package)


@pytest.mark.parametrize(("package", "allowed"), sorted(PROVIDER_MODULES.items()))
def test_provider_imports_confined(package: str, allowed: str) -> None:
    """F01 R16 : yfinance/pandas dans `data/source.py` seulement, calendrier dans `calendar.py`."""
    offenders = [
        loc for loc in _imports_of(REPO_ROOT / "src", package) if not loc.startswith(f"{allowed}:")
    ]

    assert offenders == []


def test_imports_of_detects_violation(tmp_path: Path) -> None:
    """Garde-fou du détecteur : un import interdit est bien trouvé (absolu, `from`, sous-module)."""
    (tmp_path / "a.py").write_text("import pandas as pd\n", encoding="utf-8")
    (tmp_path / "b.py").write_text(
        "from yfinance.utils import x\nfrom . import pandas\n", encoding="utf-8"
    )

    assert _imports_of(tmp_path, "pandas") == ["a.py:1"]
    assert _imports_of(tmp_path, "yfinance") == ["b.py:1"]


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


def test_readme_documents_ingest_and_schemas() -> None:
    """F01 (T18) : commandes `th ingest` / `th schemas`, options, codes de sortie, TH_DATA_DIR."""
    readme = _readme()

    for expected in (
        "uv run th ingest",
        "--symbols",
        "--full",
        "--start",
        "uv run th schemas",
        "TH_DATA_DIR",
        "data/runs/",
    ):
        assert expected in readme, expected
    for code in ("`0`", "`1`", "`2`"):
        assert code in readme, code


def test_docs_list_new_data_modules() -> None:
    """F01 (plan, décision 1) : `data/source.py` est un module à effets de bord documenté."""
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    architecture = (REPO_ROOT / "specs" / "02-architecture.md").read_text(encoding="utf-8")

    assert "data/source.py" in claude_md
    assert "TH_DATA_DIR" in claude_md
    assert "source.py" in architecture
    assert "bars.py" in architecture


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


# --- Workflow CI (R15, R16, R17) ----------------------------------------------------------------

CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _ci() -> dict[str, Any]:
    data = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # YAML 1.1 : la clé `on` est lue comme le booléen True par PyYAML.
    if True in data:
        data["on"] = data.pop(True)
    return data


def _steps(job: str) -> list[dict[str, Any]]:
    steps = _ci()["jobs"][job]["steps"]
    assert isinstance(steps, list)
    return steps


def _run_commands(job: str) -> str:
    return "\n".join(str(step.get("run", "")) for step in _steps(job))


def test_ci_triggers_on_main_push_and_pull_requests() -> None:
    triggers = _ci()["on"]

    assert triggers["push"]["branches"] == ["main"]
    assert "pull_request" in triggers


def test_ci_declares_read_only_permissions() -> None:
    assert _ci()["permissions"] == {"contents": "read"}


def test_ci_cancels_superseded_runs() -> None:
    concurrency = _ci()["concurrency"]

    assert "github.ref" in concurrency["group"]
    assert concurrency["cancel-in-progress"] is True


@pytest.mark.parametrize("job", ["python", "dashboard"])
def test_ci_job_has_timeout_and_ubuntu_runner(job: str) -> None:
    config = _ci()["jobs"][job]

    assert config["runs-on"] == "ubuntu-latest"
    assert 0 < config["timeout-minutes"] <= 15


def test_ci_actions_pinned_by_sha() -> None:
    uses = re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", CI_WORKFLOW.read_text(encoding="utf-8"), re.M)

    assert uses, "aucune action trouvée"
    for action in uses:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", action), action


def test_ci_uses_no_secrets() -> None:
    assert "secrets." not in CI_WORKFLOW.read_text(encoding="utf-8")


def test_ci_python_job_runs_quality_gates() -> None:
    commands = _run_commands("python")

    for command in (
        "uv lock --check",
        "uv sync --locked",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy --strict src/",
        "uv run pytest",
    ):
        assert command in commands, command


def test_ci_dashboard_job_runs_quality_gates() -> None:
    commands = _run_commands("dashboard")

    for command in (
        "npm ci",
        "npm run lint",
        "npm run typecheck",
        "npm run build",
        "npm run check:dist",
        "TH_DASHBOARD_BASE: /TradingHelper/",
    ):
        assert command in commands or command in CI_WORKFLOW.read_text(encoding="utf-8"), command


def test_license_forced_lf() -> None:
    result = _git("check-attr", "eol", "--", "LICENSE")

    assert result.stdout.strip() == "LICENSE: eol: lf"
