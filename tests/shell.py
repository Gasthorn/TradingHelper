"""Localisation de bash pour les tests qui exécutent des scripts shell (F10)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def find_bash() -> str | None:
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
