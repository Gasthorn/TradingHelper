"""Tests d'hygiène du dépôt (F00 — R1, R4, R5, R15 à R21)."""

from __future__ import annotations

import ast
import importlib
import re
import socket
import subprocess
import tomllib
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
    "dashboard/dist-base/index.html",  # F09 R25 : builds e2e
    "dashboard/test-results/results.json",
    "dashboard/playwright-report/index.html",
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
# F10 (T5) : un script bash en CRLF échoue sous Linux.
LF_EXTENSIONS_SCRIPTS = ["sh"]


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


@pytest.mark.parametrize(
    "extension", LF_EXTENSIONS + LF_EXTENSIONS_DASHBOARD + LF_EXTENSIONS_SCRIPTS
)
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


#: F08 (T1) : paquets importés directement, non confinés à un module.
DIRECT_PACKAGES = ("numpy", "hypothesis", "jsonschema")


@pytest.mark.parametrize("package", sorted(PROVIDER_MODULES) + list(DIRECT_PACKAGES))
# À l'import, urllib3 (tiré par yfinance) sonde IPv6 en créant une socket locale sur `::1`, sans
# réseau, et ignore l'échec : pytest-socket la bloque et émet ce UserWarning, sans conséquence.
@pytest.mark.filterwarnings("ignore:A test tried to use socket:UserWarning")
def test_provider_packages_importable(package: str) -> None:
    """F01 R5, R16, F08 R7/R8/R1 : dépendances déclarées et importables sans réseau."""
    importlib.import_module(package)


def _declared(requirements: list[str]) -> set[str]:
    """Noms de paquets d'une liste de spécifications PEP 508 (`numpy>=2.5` → `numpy`)."""
    return {re.split(r"[<>=!~;\[ ]", req, maxsplit=1)[0].lower() for req in requirements}


def test_direct_dependencies_declared() -> None:
    """F08 (plan) : numpy importé par `features/` est une dépendance directe, pas seulement
    transitive ; hypothesis et jsonschema ne servent qu'aux tests (groupe `dev`)."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    runtime = _declared(pyproject["project"]["dependencies"])
    dev = _declared(pyproject["dependency-groups"]["dev"])

    assert "numpy" in runtime
    assert {"hypothesis", "jsonschema"} <= dev
    assert not {"hypothesis", "jsonschema"} & runtime


@pytest.mark.parametrize(("package", "allowed"), sorted(PROVIDER_MODULES.items()))
def test_provider_imports_confined(package: str, allowed: str) -> None:
    """F01 R16 : yfinance/pandas dans `data/source.py` seulement, calendrier dans `calendar.py`."""
    offenders = [
        loc for loc in _imports_of(REPO_ROOT / "src", package) if not loc.startswith(f"{allowed}:")
    ]

    assert offenders == []


@pytest.mark.parametrize(
    "package",
    [
        "os",
        "pathlib",
        "io",
        "shutil",
        "tempfile",
        "tradinghelper.data.storage",
        "tradinghelper.data.calendar",
    ],
)
def test_quality_module_is_pure(package: str) -> None:
    """F02 (plan) : `data/quality.py` ne fait aucune E/S ; le calendrier y entre en fonction."""
    data_pkg = REPO_ROOT / "src" / "tradinghelper" / "data"
    offenders = [loc for loc in _imports_of(data_pkg, package) if loc.startswith("quality.py:")]

    assert offenders == []


def test_quality_module_never_opens_files() -> None:
    path = REPO_ROOT / "src" / "tradinghelper" / "data" / "quality.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"
    ]

    assert calls == []


#: F08 (T2) : `features/indicators.py` est pur et ne dépend que de numpy (pas de pandas, ni E/S).
INDICATORS_ALLOWED_IMPORTS = frozenset({"__future__", "typing", "numpy"})


def test_indicators_module_is_pure() -> None:
    path = REPO_ROOT / "src" / "tradinghelper" / "features" / "indicators.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            roots.add("." if node.level else (node.module or "").split(".")[0])
    opens = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"
    ]

    assert roots <= INDICATORS_ALLOWED_IMPORTS, roots - INDICATORS_ALLOWED_IMPORTS
    assert opens == []


#: F08 (plan) : `export/build.py` construit les fichiers en mémoire, sans aucune E/S.
BUILD_FORBIDDEN_IMPORTS = (
    "os",
    "pathlib",
    "io",
    "shutil",
    "tempfile",
    "subprocess",
    "tradinghelper.data.storage",
)


@pytest.mark.parametrize("package", BUILD_FORBIDDEN_IMPORTS)
def test_build_module_is_pure(package: str) -> None:
    export_pkg = REPO_ROOT / "src" / "tradinghelper" / "export"
    offenders = [loc for loc in _imports_of(export_pkg, package) if loc.startswith("build.py:")]

    assert offenders == []


def test_build_module_never_opens_files() -> None:
    path = REPO_ROOT / "src" / "tradinghelper" / "export" / "build.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"
    ]

    assert path.is_file()
    assert calls == []


#: F10 (T3) : `orchestration/commit_message.py` est pur : ni E/S, ni horloge, ni calendrier.
COMMIT_MESSAGE_ALLOWED_IMPORTS = frozenset(
    {"__future__", "collections", "datetime", "typing", "tradinghelper"}
)


def test_commit_message_module_is_pure() -> None:
    path = REPO_ROOT / "src" / "tradinghelper" / "orchestration" / "commit_message.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add("." if node.level else node.module or "")
    roots = {module.split(".")[0] for module in modules}
    internal = {module for module in modules if module.startswith("tradinghelper")}
    opens = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"
    ]

    assert roots <= COMMIT_MESSAGE_ALLOWED_IMPORTS, roots - COMMIT_MESSAGE_ALLOWED_IMPORTS
    assert internal <= {"tradinghelper.schemas"}, internal
    assert opens == []


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


def test_readme_documents_validate() -> None:
    """F02 (T14) : commande `th validate`, options, codes de sortie, rapport conditionnel."""
    readme = _readme()

    assert "### `th validate`" in readme
    for expected in ("uv run th validate", "--all-history", "--symbols", "aucun rapport"):
        assert expected in readme, expected
    assert "arrivent avec les features F02" not in readme


def test_docs_list_validate_modules() -> None:
    """F02 (plan, décision 1) : `quality.py` pur, `validate.py` à effets de bord, documentés."""
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    architecture = (REPO_ROOT / "specs" / "02-architecture.md").read_text(encoding="utf-8")

    assert "data/validate.py" in claude_md
    assert "data/quality.py" in claude_md
    assert "uv run th validate" in claude_md
    assert "quality.py" in architecture


def test_readme_mentions_dashboard_url_and_github_settings() -> None:
    readme = _readme()

    assert "github.io/TradingHelper/" in readme
    assert "active après F10" not in readme  # F10 livre le déploiement
    # F10 R13 : les écritures sont accordées par les clés `permissions` des workflows ; le
    # réglage du dépôt reste en lecture seule.
    assert "Read and write permissions" not in readme


def _readme_section(heading: str) -> str:
    """Texte de la section `## heading` du README, jusqu'à la section de même niveau suivante."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", _readme(), re.M | re.S)
    assert match is not None, f"section « {heading} » absente du README"
    return " ".join(match.group(1).split())  # retours à la ligne du texte ignorés


def test_readme_has_mise_en_service_section() -> None:
    """F10 R13 : réglages manuels et relances documentés."""
    section = _readme_section("Mise en service")

    assert "Pages → Build and deployment → Source** : « GitHub Actions »" in section
    assert "Read repository contents" in section
    assert "`permissions`" in section
    assert "github-actions[bot]" in section  # protection de `main`
    for workflow in ("daily", "backfill", "deploy-pages"):
        assert f"`{workflow}`" in section, workflow
    assert "Run workflow" in section  # relance manuelle (workflow_dispatch)


def test_readme_documents_actions_limits() -> None:
    """F10 R15 : limites de GitHub Actions acceptées et documentées."""
    section = _readme_section("Mise en service")

    assert "un seul run en attente" in section  # file d'attente `concurrency`
    assert "retardés ou sautés" in section  # cron
    assert "déploiement échoue" in section
    assert "notifications" in section


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


def _step_index(job: str, command: str) -> int:
    for index, step in enumerate(_steps(job)):
        if command in str(step.get("run", "")):
            return index
    raise AssertionError(f"aucune étape `{command}` dans le job {job}")


def test_ci_dashboard_job_checks_generated_types() -> None:
    """F08 R5 : la CI échoue si `npm run gen:types` modifie ou ajoute un fichier de src/types/.

    `git status --porcelain` (et non `git diff`) détecte aussi un type non commité (nouveau
    schéma), qu'un `git diff` ignorerait car le fichier serait non suivi.
    """
    gen = _step_index("dashboard", "npm run gen:types")
    run = str(_steps("dashboard")[gen]["run"])

    assert 'test -z "$(git status --porcelain -- src/types)"' in run
    assert _step_index("dashboard", "npm ci") < gen < _step_index("dashboard", "npm run typecheck")


def test_ci_dashboard_job_runs_dashboard_tests() -> None:
    """F09 R25 : le job `dashboard` lance Vitest, installe Chromium (et ses dépendances système),
    puis les tests e2e Playwright, après le contrôle des types générés."""
    gen = _step_index("dashboard", "npm run gen:types")
    unit = _step_index("dashboard", "npm test")
    install = _step_index("dashboard", "playwright install --with-deps chromium")
    e2e = _step_index("dashboard", "npm run test:e2e")

    assert gen < unit < install < e2e


def test_ci_dashboard_job_caches_playwright_browsers() -> None:
    """F09 (T23) : navigateurs Playwright en cache, clé liée à la version de @playwright/test."""
    cache = [s for s in _steps("dashboard") if str(s.get("uses", "")).startswith("actions/cache@")]

    assert len(cache) == 1
    assert cache[0]["with"]["path"] == "~/.cache/ms-playwright"
    assert "playwright" in str(cache[0]["with"]["key"])
    assert _steps("dashboard").index(cache[0]) < _step_index("dashboard", "playwright install")


def test_readme_documents_export() -> None:
    """F08 (T23) : commande `th export`, `--out`, codes de sortie, types TS générés."""
    readme = _readme()

    assert "### `th export`" in readme
    for expected in (
        "uv run th export",
        "--out",
        "dashboard/public/data",
        "manifest.json",
        "npm run gen:types",
        "aucun fichier n'est écrit",
    ):
        assert expected in readme, expected
    assert "arrivent avec les features F08" not in readme


def test_docs_list_export_modules() -> None:
    """F08 (plan, décision 6) : `export/build.py` pur, `export/dashboard.py` à effets de bord."""
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    architecture = (REPO_ROOT / "specs" / "02-architecture.md").read_text(encoding="utf-8")
    pure, side_effects = next(
        line for line in claude_md.splitlines() if line.startswith("- Fonctions pures")
    ).split("effets de bord", 1)

    assert "export/build.py" in pure
    assert "export/dashboard.py" in side_effects
    assert "uv run th export" in claude_md
    assert "npm run gen:types" in claude_md
    assert "build.py" in architecture


def test_readme_documents_commit_message() -> None:
    """F10 (T12) : `th commit-message` dans le tableau des commandes `th`."""
    readme = _readme()

    assert "| `uv run th commit-message --kind daily --since T0` |" in readme
    assert "arrivent avec les features F07" in readme  # signaux, paper : toujours à venir


def test_docs_list_orchestration_modules() -> None:
    """F10 (plan) : `orchestration/commit_message.py` pur ; `scripts/ci/` dans l'arborescence."""
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    architecture = (REPO_ROOT / "specs" / "02-architecture.md").read_text(encoding="utf-8")
    pure, _side_effects = next(
        line for line in claude_md.splitlines() if line.startswith("- Fonctions pures")
    ).split("effets de bord", 1)

    assert "orchestration/commit_message.py" in pure
    assert "uv run th commit-message" in claude_md
    assert "scripts/ci/commit-and-push.sh" in claude_md
    assert "orchestration/" in architecture
    assert "commit-and-push.sh" in architecture
