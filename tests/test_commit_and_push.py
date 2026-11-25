"""Tests de `scripts/ci/commit-and-push.sh` (F10 R3, R4).

Le script est exécuté par `bash` contre un dépôt distant local (`git init --bare`) : aucun réseau.
La configuration git de l'utilisateur est isolée (`GIT_CONFIG_GLOBAL`, `GIT_CONFIG_NOSYSTEM`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "commit-and-push.sh"

BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def _find_bash() -> str | None:
    """Bash de Git for Windows sous Windows (jamais celui de WSL), sinon celui du PATH."""
    if sys.platform == "win32":
        git = shutil.which("git")
        if git is None:
            return None
        for root in Path(git).resolve().parents:
            for candidate in (root / "usr" / "bin" / "bash.exe", root / "bin" / "bash.exe"):
                if candidate.is_file():
                    return str(candidate)
        return None
    return shutil.which("bash")


BASH = _find_bash()

pytestmark = pytest.mark.skipif(BASH is None, reason="bash introuvable")


@dataclass
class _Repo:
    """Un clone de travail `work` et son distant nu `remote`."""

    root: Path
    work: Path
    remote: Path
    env: dict[str, str]

    def git(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or self.work,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout.strip()

    def write(self, relative: str, content: str) -> None:
        path = self.work / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def run_script(self, message: str, *paths: str) -> subprocess.CompletedProcess[str]:
        assert BASH is not None
        return subprocess.run(
            [BASH, SCRIPT.as_posix(), message, *paths],
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def outputs(self) -> dict[str, str]:
        lines = Path(self.env["GITHUB_OUTPUT"]).read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines if "=" in line)

    def remote_head(self) -> str:
        return self.git("rev-parse", "refs/heads/main", cwd=self.remote)


@pytest.fixture
def repo(tmp_path: Path) -> _Repo:
    global_config = tmp_path / "gitconfig"
    global_config.write_text(
        "[user]\n\tname = Humain\n\temail = humain@example.invalid\n"
        "[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n",
        encoding="utf-8",
    )
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(global_config),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GITHUB_OUTPUT": str(output),
        "TH_PUSH_SLEEP": "0",
    }
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        env.pop(name, None)
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], env=env, check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], env=env, check=True)
    repo = _Repo(tmp_path, work, remote, env)
    repo.write("data/raw/prices/AAPL.json", "{}\n")
    repo.write("README.md", "x\n")
    repo.git("add", ".")
    repo.git("commit", "-q", "-m", "init")
    repo.git("push", "-q", "origin", "main")
    return repo


def test_untracked_file_is_committed(repo: _Repo) -> None:
    repo.write("data/runs/2026-11-23.json", "{}\n")

    result = repo.run_script("data: daily update 2026-11-23", "data/")

    assert result.returncode == 0, result.stderr
    assert repo.git("log", "-1", "--format=%s", cwd=repo.remote) == "data: daily update 2026-11-23"
    files = repo.git("show", "--name-only", "--format=", "main", cwd=repo.remote).splitlines()
    assert files == ["data/runs/2026-11-23.json"]


def test_no_change_no_commit_empty_pushed_sha(repo: _Repo) -> None:
    before = repo.remote_head()

    result = repo.run_script("data: daily update 2026-11-23", "data/")

    assert result.returncode == 0, result.stderr
    assert repo.remote_head() == before
    assert repo.outputs() == {"pushed_sha": "", "head_sha": before}


def test_only_given_paths_are_committed(repo: _Repo) -> None:
    repo.write("data/raw/prices/AAPL.json", '{"a": 1}\n')
    repo.write("README.md", "modifié\n")
    repo.write("dashboard/public/data/manifest.json", "{}\n")

    result = repo.run_script("data: daily update 2026-11-23", "data/")

    assert result.returncode == 0, result.stderr
    files = repo.git("show", "--name-only", "--format=", "main", cwd=repo.remote).splitlines()
    assert files == ["data/raw/prices/AAPL.json"]
    status = repo.git("status", "--porcelain", "--untracked-files=all").splitlines()
    assert sorted(line.split()[-1] for line in status) == [
        "README.md",
        "dashboard/public/data/manifest.json",
    ]


def test_author_is_github_actions_bot(repo: _Repo) -> None:
    repo.write("data/runs/2026-11-23.json", "{}\n")

    repo.run_script("data: daily update 2026-11-23", "data/")

    identity = repo.git("log", "-1", "--format=%an <%ae>|%cn <%ce>", cwd=repo.remote)
    assert identity == f"{BOT_NAME} <{BOT_EMAIL}>|{BOT_NAME} <{BOT_EMAIL}>"


def test_outputs_written_to_github_output(repo: _Repo) -> None:
    repo.write("data/runs/2026-11-23.json", "{}\n")

    result = repo.run_script("data: daily update 2026-11-23", "data/")

    assert result.returncode == 0, result.stderr
    head = repo.remote_head()
    assert repo.outputs() == {"pushed_sha": head, "head_sha": head}
    assert repo.git("rev-parse", "HEAD") == head


def test_usage_error_without_paths(repo: _Repo) -> None:
    result = repo.run_script("data: daily update 2026-11-23")

    assert result.returncode == 2
    assert "Usage" in result.stderr


# --- pull --rebase et tentatives (R4) ------------------------------------------------------------


def _other_clone(repo: _Repo) -> _Repo:
    """Second clone du même distant, pour simuler un push concurrent."""
    other = repo.root / "other"
    subprocess.run(["git", "clone", "-q", str(repo.remote), str(other)], env=repo.env, check=True)
    return _Repo(repo.root, other, repo.remote, repo.env)


def test_rebases_over_concurrent_push(repo: _Repo) -> None:
    other = _other_clone(repo)
    other.write("README.md", "modifié ailleurs\n")
    other.git("commit", "-q", "-am", "humain")
    other.git("push", "-q", "origin", "main")
    repo.write("data/runs/2026-11-23.json", "{}\n")

    result = repo.run_script("data: daily update 2026-11-23", "data/")

    assert result.returncode == 0, result.stderr
    log = repo.git("log", "--format=%s", "main", cwd=repo.remote).splitlines()
    assert log == ["data: daily update 2026-11-23", "humain", "init"]
    merges = repo.git("rev-list", "--merges", "main", cwd=repo.remote)
    assert merges == ""
    assert repo.outputs()["pushed_sha"] == repo.remote_head()


def test_fails_after_three_attempts(repo: _Repo) -> None:
    hook = repo.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho refus >&2\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    before = repo.remote_head()
    repo.write("data/runs/2026-11-23.json", "{}\n")

    result = repo.run_script("data: daily update 2026-11-23", "data/")

    assert result.returncode == 1
    assert [line for line in result.stderr.splitlines() if "Tentative de push" in line] == [
        "Tentative de push 1/3",
        "Tentative de push 2/3",
        "Tentative de push 3/3",
    ]
    assert "échec" in result.stderr
    assert repo.remote_head() == before


def test_rebase_conflict_is_aborted(repo: _Repo) -> None:
    other = _other_clone(repo)
    other.write("data/raw/prices/AAPL.json", '{"autre": 1}\n')
    other.git("commit", "-q", "-am", "humain")
    other.git("push", "-q", "origin", "main")
    before = repo.remote_head()
    repo.write("data/raw/prices/AAPL.json", '{"bot": 1}\n')

    result = repo.run_script("data: daily update 2026-11-23", "data/")

    assert result.returncode == 1
    assert repo.remote_head() == before
    git_dir = repo.work / ".git"
    assert not (git_dir / "rebase-merge").exists()
    assert not (git_dir / "rebase-apply").exists()
    assert repo.git("log", "-1", "--format=%s") == "data: daily update 2026-11-23"
