"""Structure des workflows GitHub Actions de F10 (R1, R2, R4 à R12, R14).

Les workflows ne sont pas exécutables localement de bout en bout (OIDC, Pages) : on vérifie leur
structure en lisant le YAML (PyYAML), puis par des runs réels (T13).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

#: Action tierce épinglée par SHA de commit complet (R11).
PINNED = re.compile(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}")

PAGES_PERMISSIONS = {"contents": "read", "pages": "write", "id-token": "write"}


def _text(name: str) -> str:
    return (WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8")


def _workflow(name: str) -> dict[str, Any]:
    data = yaml.safe_load(_text(name))
    assert isinstance(data, dict)
    # YAML 1.1 : la clé `on` est lue comme le booléen True par PyYAML.
    if True in data:
        data["on"] = data.pop(True)
    return data


def _jobs(name: str) -> dict[str, dict[str, Any]]:
    jobs = _workflow(name)["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def _steps(name: str, job: str) -> list[dict[str, Any]]:
    steps = _jobs(name)[job]["steps"]
    assert isinstance(steps, list)
    return steps


def _step_using(name: str, job: str, action: str) -> dict[str, Any]:
    matches = [s for s in _steps(name, job) if str(s.get("uses", "")).startswith(f"{action}@")]
    assert len(matches) == 1, f"{action} attendu une fois dans {name}/{job}"
    return matches[0]


def _step_running(name: str, job: str, fragment: str) -> dict[str, Any]:
    matches = [s for s in _steps(name, job) if fragment in str(s.get("run", ""))]
    assert len(matches) == 1, f"une étape `{fragment}` attendue dans {name}/{job}"
    return matches[0]


# --- deploy-pages.yml (R1, R2, R8, R10 à R12) ---------------------------------------------------


@pytest.mark.parametrize(("name", "expected"), [("deploy-pages", PAGES_PERMISSIONS)])
def test_workflow_level_permissions(name: str, expected: dict[str, str]) -> None:
    assert _workflow(name)["permissions"] == expected


def test_deploy_pages_job_permissions() -> None:
    """R1 : chaque job déclare ses permissions, sans dépasser le tableau de la spec."""
    jobs = _jobs("deploy-pages")

    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert jobs["deploy"]["permissions"] == {"pages": "write", "id-token": "write"}


def test_deploy_pages_uses_own_group() -> None:
    concurrency = _workflow("deploy-pages")["concurrency"]

    assert concurrency == {"group": "pages", "cancel-in-progress": False}
    for job, config in _jobs("deploy-pages").items():
        assert "concurrency" not in config, job


def test_deploy_pages_triggers() -> None:
    triggers = _workflow("deploy-pages")["on"]

    assert set(triggers) == {"workflow_call", "push", "workflow_dispatch"}
    ref = triggers["workflow_call"]["inputs"]["ref"]
    assert ref["type"] == "string"
    assert ref["required"] is False


def test_deploy_pages_push_paths() -> None:
    push = _workflow("deploy-pages")["on"]["push"]

    assert push["branches"] == ["main"]
    assert push["paths"] == [
        "dashboard/**",
        "src/**",
        "config/**",
        "data/**",
        "models/**",
        "pyproject.toml",
        "uv.lock",
    ]


def test_deploy_checks_out_ref_and_sets_th_git_sha() -> None:
    """R8 : on publie le SHA demandé, et le manifest porte ce SHA (pas `GITHUB_SHA`)."""
    checkout = _step_using("deploy-pages", "build", "actions/checkout")
    export = _step_running("deploy-pages", "build", "th export")

    assert checkout["with"]["ref"] == "${{ inputs.ref || github.sha }}"
    assert 'TH_GIT_SHA="$(git rev-parse HEAD)"' in export["run"]
    steps = _steps("deploy-pages", "build")
    assert steps.index(checkout) < steps.index(export)


def test_deploy_pages_builds_with_base_and_checks_dist() -> None:
    build = _step_running("deploy-pages", "build", "npm run build")
    upload = _step_using("deploy-pages", "build", "actions/upload-pages-artifact")
    steps = _steps("deploy-pages", "build")

    assert build["env"]["TH_DASHBOARD_BASE"] == "/${{ github.event.repository.name }}/"
    assert "npm run check:dist" in build["run"]
    assert build["working-directory"] == "dashboard"
    assert upload["with"]["path"] == "dashboard/dist"
    assert steps.index(_step_running("deploy-pages", "build", "th export")) < steps.index(build)
    assert steps.index(build) < steps.index(upload)


def test_deploy_pages_deploy_job() -> None:
    deploy = _jobs("deploy-pages")["deploy"]

    assert deploy["needs"] == "build"
    assert deploy["environment"]["name"] == "github-pages"
    _step_using("deploy-pages", "deploy", "actions/deploy-pages")


@pytest.mark.parametrize("name", ["deploy-pages"])
def test_actions_pinned_by_sha(name: str) -> None:
    uses = re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", _text(name), re.M)

    assert uses, "aucune action trouvée"
    for action in uses:
        if action.startswith("./"):  # workflow réutilisable du dépôt
            continue
        assert PINNED.fullmatch(action), action


@pytest.mark.parametrize(("name", "expected"), [("deploy-pages", {"build": 15, "deploy": 15})])
def test_job_timeouts(name: str, expected: dict[str, int]) -> None:
    """R12 : chaque job (hors appel de workflow réutilisable) a son `timeout-minutes`."""
    timeouts = {
        job: config.get("timeout-minutes")
        for job, config in _jobs(name).items()
        if "uses" not in config
    }

    assert timeouts == expected


@pytest.mark.parametrize("name", ["deploy-pages"])
def test_jobs_run_on_ubuntu_latest(name: str) -> None:
    for job, config in _jobs(name).items():
        if "uses" not in config:
            assert config["runs-on"] == "ubuntu-latest", job


@pytest.mark.parametrize("name", ["deploy-pages"])
def test_no_user_input_interpolated_in_run(name: str) -> None:
    """R14 : une valeur fournie par l'utilisateur passe par `env:`, jamais dans un `run:`."""
    for job in _jobs(name):
        for step in _jobs(name)[job].get("steps", []):
            run = str(step.get("run", ""))
            assert "${{ inputs." not in run, (job, step.get("name"))
            assert "${{ github.event.inputs." not in run, (job, step.get("name"))
