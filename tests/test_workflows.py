"""Structure des workflows GitHub Actions de F10 (R1, R2, R4 à R12, R14).

Les workflows ne sont pas exécutables localement de bout en bout (OIDC, Pages) : on vérifie leur
structure en lisant le YAML (PyYAML), puis par des runs réels (T13).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from shell import find_bash

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


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("deploy-pages", PAGES_PERMISSIONS),
        ("daily", {"contents": "read"}),
        ("backfill", {"contents": "read"}),
    ],
)
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


@pytest.mark.parametrize("name", ["deploy-pages", "daily", "backfill"])
def test_actions_pinned_by_sha(name: str) -> None:
    uses = re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", _text(name), re.M)

    assert uses, "aucune action trouvée"
    for action in uses:
        if action.startswith("./"):  # workflow réutilisable du dépôt
            continue
        assert PINNED.fullmatch(action), action


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("deploy-pages", {"build": 15, "deploy": 15}),
        ("daily", {"pipeline": 30, "conclude": 5}),
        ("backfill", {"pipeline": 30, "conclude": 5}),
    ],
)
def test_job_timeouts(name: str, expected: dict[str, int]) -> None:
    """R12 : chaque job (hors appel de workflow réutilisable) a son `timeout-minutes`."""
    timeouts = {
        job: config.get("timeout-minutes")
        for job, config in _jobs(name).items()
        if "uses" not in config
    }

    assert timeouts == expected


@pytest.mark.parametrize("name", ["deploy-pages", "daily", "backfill"])
def test_jobs_run_on_ubuntu_latest(name: str) -> None:
    for job, config in _jobs(name).items():
        if "uses" not in config:
            assert config["runs-on"] == "ubuntu-latest", job


@pytest.mark.parametrize("name", ["deploy-pages", "daily", "backfill"])
def test_no_user_input_interpolated_in_run(name: str) -> None:
    """R14 : une valeur fournie par l'utilisateur passe par `env:`, jamais dans un `run:`."""
    for job in _jobs(name):
        for step in _jobs(name)[job].get("steps", []):
            run = str(step.get("run", ""))
            assert "${{ inputs." not in run, (job, step.get("name"))
            assert "${{ github.event.inputs." not in run, (job, step.get("name"))


# --- daily.yml : job `pipeline` (R1, R2, R4 à R7, R11, R12) ------------------------------------

DATA_WRITERS = ["daily", "backfill"]


def _step_id(name: str, job: str, step_id: str) -> dict[str, Any]:
    matches = [s for s in _steps(name, job) if s.get("id") == step_id]
    assert len(matches) == 1, f"étape `{step_id}` attendue dans {name}/{job}"
    return matches[0]


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_pipeline_job_permissions(name: str) -> None:
    assert _jobs(name)["pipeline"]["permissions"] == {"contents": "write"}


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_data_writers_share_group(name: str) -> None:
    assert _workflow(name)["concurrency"] == {"group": "data-writer", "cancel-in-progress": False}
    for job, config in _jobs(name).items():
        assert "concurrency" not in config, job


def test_daily_triggers() -> None:
    triggers = _workflow("daily")["on"]

    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert triggers["schedule"] == [{"cron": "30 22 * * 1-5"}]


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_pipeline_step_order(name: str) -> None:
    steps = _steps(name, "pipeline")
    order = [
        _step_id(name, "pipeline", "t0"),
        _step_id(name, "pipeline", "ingest"),
        _step_running(name, "pipeline", "th validate"),
        _step_id(name, "pipeline", "commit"),
        _step_using(name, "pipeline", "actions/upload-artifact"),
    ]

    assert [steps.index(step) for step in order] == sorted(steps.index(step) for step in order)


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_pipeline_outputs(name: str) -> None:
    assert _jobs(name)["pipeline"]["outputs"] == {
        "pushed_sha": "${{ steps.commit.outputs.pushed_sha }}",
        "head_sha": "${{ steps.commit.outputs.head_sha }}",
        "ingest_exit_code": "${{ steps.ingest.outputs.exit_code }}",
    }


def _run_ingest_step(
    name: str, uv_exit: int, tmp_path: Path, inputs: dict[str, str] | None = None
) -> tuple[int, str, list[str]]:
    """Exécute le script de l'étape `ingest` comme GitHub Actions (`bash -eo pipefail`), avec
    une fonction `uv` qui note ses arguments et sort avec `uv_exit`. `inputs` : variables
    d'environnement de l'étape (valeurs saisies au lancement). Renvoie (code, contenu de
    GITHUB_OUTPUT, arguments reçus par `uv`)."""
    bash = find_bash()
    if bash is None:
        pytest.skip("bash introuvable")
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    uv_args = tmp_path / "uv_args"
    fake_uv = f'uv() {{ printf "%s\\n" "$@" > "$UV_ARGS"; return {uv_exit}; }}'
    script = f"{fake_uv}\n{_step_id(name, 'pipeline', 'ingest')['run']}"
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        env={
            "GITHUB_OUTPUT": str(output),
            "UV_ARGS": str(uv_args),
            "PATH": "/usr/bin:/bin",
            **(inputs or {}),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    received = uv_args.read_text(encoding="utf-8").splitlines() if uv_args.exists() else []
    return result.returncode, output.read_text(encoding="utf-8"), received


@pytest.mark.parametrize("name", DATA_WRITERS)
@pytest.mark.parametrize(("uv_exit", "step_exit"), [(0, 0), (1, 0), (2, 2)])
def test_ingest_exit_2_stops_and_1_continues(
    name: str, uv_exit: int, step_exit: int, tmp_path: Path
) -> None:
    """R7 : code 2 → arrêt ; code 1 → on continue, code mémorisé pour le job `conclude`."""
    code, output, _ = _run_ingest_step(name, uv_exit, tmp_path)

    assert code == step_exit
    assert output.splitlines() == [f"exit_code={uv_exit}"]


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_validate_step_not_continue_on_error(name: str) -> None:
    step = _step_running(name, "pipeline", "th validate")

    assert "continue-on-error" not in step
    assert "if" not in step


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_commit_step_only_on_main(name: str) -> None:
    assert _step_id(name, "pipeline", "commit")["if"] == "github.ref == 'refs/heads/main'"


@pytest.mark.parametrize(("name", "kind"), [("daily", "daily"), ("backfill", "backfill")])
def test_commit_uses_commit_message_and_data_path(name: str, kind: str) -> None:
    step = _step_id(name, "pipeline", "commit")
    run = step["run"]

    assert step["env"]["T0"] == "${{ steps.t0.outputs.value }}"
    assert f'th commit-message --kind {kind} --since "$T0"' in run
    assert 'bash scripts/ci/commit-and-push.sh "$MSG" data/' in run
    assert "dashboard" not in run


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_report_artifact_always_uploaded(name: str) -> None:
    step = _step_using(name, "pipeline", "actions/upload-artifact")

    assert step["if"] == "always()"
    assert step["with"]["path"] == "data/runs/"
    assert step["with"]["if-no-files-found"] == "ignore"
    assert step["with"]["retention-days"] == 30


# --- daily.yml : jobs `deploy` et `conclude` (R1, R7, R9) ---------------------------------------


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_caller_job_grants_pages_permissions(name: str) -> None:
    """R1 : le job appelant accorde lui-même les permissions du workflow réutilisable."""
    deploy = _jobs(name)["deploy"]

    assert deploy["uses"] == "./.github/workflows/deploy-pages.yml"
    assert deploy["permissions"] == PAGES_PERMISSIONS


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_deploy_condition(name: str) -> None:
    """R9 : déploiement SSI commit poussé, ou lancement manuel sur main."""
    deploy = _jobs(name)["deploy"]

    assert deploy["needs"] == "pipeline"
    assert deploy["if"] == (
        "needs.pipeline.outputs.pushed_sha != '' || "
        "(github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main')"
    )


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_deploy_ref_is_pushed_or_head_sha(name: str) -> None:
    assert _jobs(name)["deploy"]["with"] == {
        "ref": "${{ needs.pipeline.outputs.pushed_sha || needs.pipeline.outputs.head_sha }}"
    }


@pytest.mark.parametrize("name", DATA_WRITERS)
def test_conclude_runs_always(name: str) -> None:
    conclude = _jobs(name)["conclude"]

    assert conclude["needs"] == ["pipeline", "deploy"]
    assert conclude["if"] == "always()"
    assert conclude["permissions"] == {}
    assert conclude["env"] == {
        "PIPELINE_RESULT": "${{ needs.pipeline.result }}",
        "DEPLOY_RESULT": "${{ needs.deploy.result }}",
        "INGEST_EXIT_CODE": "${{ needs.pipeline.outputs.ingest_exit_code }}",
    }


def _run_conclude(name: str, pipeline: str, deploy: str, ingest: str) -> int:
    """Exécute le script du job `conclude` comme GitHub Actions ; renvoie son code."""
    bash = find_bash()
    if bash is None:
        pytest.skip("bash introuvable")
    (step,) = _steps(name, "conclude")
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        env={
            "PATH": "/usr/bin:/bin",
            "PIPELINE_RESULT": pipeline,
            "DEPLOY_RESULT": deploy,
            "INGEST_EXIT_CODE": ingest,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


@pytest.mark.parametrize("name", DATA_WRITERS)
@pytest.mark.parametrize(
    ("pipeline", "deploy", "ingest", "ok"),
    [
        ("success", "success", "0", True),
        ("success", "skipped", "0", True),  # jour férié : rien à commiter, pas de deploy
        ("success", "success", "1", False),  # R7 : ingestion en échec, publiée puis rouge
        ("success", "skipped", "1", False),
        ("failure", "skipped", "0", False),  # ex. th validate en code 1
        ("failure", "skipped", "", False),  # ex. th ingest en code 2
        ("cancelled", "skipped", "", False),
        ("success", "failure", "0", False),
        ("success", "cancelled", "0", False),
    ],
)
def test_conclude_outcome(name: str, pipeline: str, deploy: str, ingest: str, ok: bool) -> None:
    code = _run_conclude(name, pipeline, deploy, ingest)

    assert (code == 0) is ok


# --- backfill.yml : inputs passés par `env:` (R14) -----------------------------------------------

NO_INPUTS = {"TH_IN_SYMBOLS": "", "TH_IN_FULL": "false", "TH_IN_START": ""}


def test_backfill_triggers_and_inputs() -> None:
    triggers = _workflow("backfill")["on"]

    assert set(triggers) == {"workflow_dispatch"}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"symbols", "full", "start"}
    assert inputs["symbols"]["type"] == "string"
    assert inputs["symbols"]["required"] is False
    assert inputs["full"]["type"] == "boolean"
    assert inputs["full"]["default"] is False
    assert inputs["start"]["type"] == "string"
    assert inputs["start"]["required"] is False


def test_backfill_ingest_step_reads_inputs_from_env() -> None:
    assert _step_id("backfill", "pipeline", "ingest")["env"] == {
        "TH_IN_SYMBOLS": "${{ inputs.symbols }}",
        "TH_IN_FULL": "${{ inputs.full }}",
        "TH_IN_START": "${{ inputs.start }}",
    }


def test_daily_ingest_has_no_arguments(tmp_path: Path) -> None:
    _, _, received = _run_ingest_step("daily", 0, tmp_path)

    assert received == ["run", "th", "ingest"]


@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        ({}, []),
        ({"TH_IN_SYMBOLS": "AAPL,MSFT"}, ["--symbols", "AAPL,MSFT"]),
        ({"TH_IN_SYMBOLS": "AAPL", "TH_IN_FULL": "true"}, ["--symbols", "AAPL", "--full"]),
        (
            {"TH_IN_FULL": "true", "TH_IN_START": "2015-01-01"},
            ["--full", "--start", "2015-01-01"],
        ),
        # Validation déléguée à F01 R13 : `--start` sans `--full` est transmis, th sort en 2.
        ({"TH_IN_START": "2015-01-01"}, ["--start", "2015-01-01"]),
    ],
    ids=["aucun", "symbols", "symbols-full", "full-start", "start-seul"],
)
def test_backfill_ingest_arguments(
    inputs: dict[str, str], expected: list[str], tmp_path: Path
) -> None:
    code, _, received = _run_ingest_step("backfill", 0, tmp_path, {**NO_INPUTS, **inputs})

    assert code == 0
    assert received == ["run", "th", "ingest", *expected]


def test_backfill_input_is_never_executed(tmp_path: Path) -> None:
    """R14 : une valeur malveillante reste un argument littéral, jamais une commande."""
    marker = tmp_path / "pwned"
    payload = f'AAPL"; touch {marker.as_posix()}; echo "$(touch {marker.as_posix()})'
    inputs = {**NO_INPUTS, "TH_IN_SYMBOLS": payload}

    code, _, received = _run_ingest_step("backfill", 0, tmp_path, inputs)

    assert code == 0
    assert received == ["run", "th", "ingest", "--symbols", payload]
    assert not marker.exists()
