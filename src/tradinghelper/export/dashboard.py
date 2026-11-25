"""Orchestration de `th export` (F08) : lecture des sources, rendu, écriture du dossier.

Effets de bord fichiers isolés ici (CLAUDE.md) ; la construction des fichiers est pure
(`export/build.py`). Aucune écriture dans `data/` : l'export ne modifie aucune source (R1).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ValidationError

from tradinghelper.config import UniverseConfig, universe_targets
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.storage import PricesFileError, prices_path, read_json, read_prices
from tradinghelper.export.build import (
    build_health,
    build_manifest,
    build_overview,
    build_ticker,
    collect_markers,
    compute_data_as_of,
    render,
)
from tradinghelper.schemas import (
    HEALTH_RUNS,
    MANIFEST_NAME,
    PricesFile,
    RunReport,
    SignalsFile,
)

#: Fichier daté `YYYY-MM-DD.json` (rapports de run, signaux) ; `latest.json` n'en est pas un.
_DATED_FILE: Final = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


@dataclass(frozen=True)
class SourceProblem:
    """Fichier source illisible ou non conforme à son contrat (R3, R13)."""

    path: Path
    reason: str

    def __str__(self) -> str:
        return f"{self.path.as_posix()}: {self.reason}"


class ExportSourceError(Exception):
    """Au moins une source invalide : l'export échoue (code 1) sans rien écrire (R3, R13)."""

    def __init__(self, problems: list[SourceProblem]) -> None:
        self.problems = problems
        super().__init__("\n".join(str(problem) for problem in problems))


@dataclass(frozen=True)
class Sources:
    """Données lues par l'export, déjà validées par leur contrat."""

    prices: dict[str, PricesFile]  # symboles exportés, dans l'ordre de `universe_targets`
    reports: list[RunReport]  # `HEALTH_RUNS` plus récents, `session_date` décroissante
    signals: list[SignalsFile]  # tous les fichiers datés, par date croissante


def _dated_files(directory: Path) -> list[tuple[date, Path]]:
    """Fichiers `YYYY-MM-DD.json` (date valide) de `directory`, par date croissante ; les autres
    noms (dont `latest.json`, temporaires, sauvegardes) sont ignorés. Dossier absent : []."""
    if not directory.is_dir():
        return []
    found: list[tuple[date, Path]] = []
    for path in directory.iterdir():
        match = _DATED_FILE.match(path.name)
        if match is None or not path.is_file():
            continue
        try:
            day = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        found.append((day, path))
    return sorted(found)


def _read_model[M: BaseModel](
    model: type[M], path: Path, problems: list[SourceProblem]
) -> M | None:
    """Lit et valide `path` ; en cas d'échec, ajoute un problème et renvoie None."""
    try:
        return model.model_validate(read_json(path))
    except PricesFileError as exc:  # illisible ou JSON invalide (erreur générique de `storage`)
        problems.append(SourceProblem(path, exc.reason))
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"]) or "(racine)"
        problems.append(
            SourceProblem(path, f"non conforme au contrat : {location}: {error['msg']}")
        )
    return None


def _read_prices(
    universe: UniverseConfig, data_root: Path, problems: list[SourceProblem]
) -> dict[str, PricesFile]:
    prices: dict[str, PricesFile] = {}
    for symbol, _start in universe_targets(universe):
        path = prices_path(data_root, symbol)
        try:
            file = read_prices(path)
        except PricesFileError as exc:
            problems.append(SourceProblem(path, exc.reason))
            continue
        if file is None:  # symbole sans fichier : signalé par health.json, non exporté
            continue
        if not file.bars:
            problems.append(SourceProblem(path, "aucune barre à exporter (règle F02 `empty_bars`)"))
            continue
        prices[symbol] = file
    return prices


def _read_reports(data_root: Path, problems: list[SourceProblem]) -> list[RunReport]:
    reports: list[RunReport] = []
    # Seuls les rapports résumés par health.json sont lus et validés (décision 4 du plan).
    for day, path in reversed(_dated_files(data_root / "runs")[-HEALTH_RUNS:]):
        report = _read_model(RunReport, path, problems)
        if report is None:
            continue
        if report.session_date != day:
            problems.append(
                SourceProblem(path, f"séance {report.session_date.isoformat()} dans le fichier")
            )
            continue
        reports.append(report)
    return reports


def _read_signals(data_root: Path, problems: list[SourceProblem]) -> list[SignalsFile]:
    signals: list[SignalsFile] = []
    for day, path in _dated_files(data_root / "signals"):
        file = _read_model(SignalsFile, path, problems)
        if file is None:
            continue
        if file.date != day:
            problems.append(SourceProblem(path, f"date {file.date.isoformat()} dans le fichier"))
            continue
        signals.append(file)
    return signals


def read_sources(universe: UniverseConfig, data_root: Path) -> Sources:
    """Lit et valide toutes les sources de l'export (R13) : une source absente donne une
    section vide ; une source invalide est collectée, et `ExportSourceError` liste tous les
    problèmes (prix, puis rapports, puis signaux) une fois la lecture terminée."""
    problems: list[SourceProblem] = []
    prices = _read_prices(universe, data_root, problems)
    reports = _read_reports(data_root, problems)
    signals = _read_signals(data_root, problems)
    if problems:
        raise ExportSourceError(problems)
    return Sources(prices=prices, reports=reports, signals=signals)


# --- Dossier de sortie (R2) --------------------------------------------------------------------


class ExportTargetError(Exception):
    """Dossier de sortie refusé (code 2, erreur d'arguments) : il serait supprimé par la
    reconstruction alors qu'il n'est pas un export (décision 2 du plan)."""


def check_target(out: Path, *, data_root: Path, repo_root: Path) -> None:
    """Refuse un `--out` dont le remplacement détruirait autre chose qu'un export précédent :
    racine du dépôt ou l'un de ses parents, dossier de données (ou dedans, ou au-dessus),
    fichier, ou dossier non vide sans `manifest.json`."""
    target = out.resolve()
    repo = repo_root.resolve()
    data = data_root.resolve()
    if repo.is_relative_to(target):
        raise ExportTargetError(f"{out} : racine du dépôt ou l'un de ses parents")
    if data.is_relative_to(target) or target.is_relative_to(data):
        raise ExportTargetError(f"{out} : recouvre le dossier de données {data_root}")
    if target.is_file():
        raise ExportTargetError(f"{out} : c'est un fichier")
    if target.is_dir() and any(target.iterdir()) and not (target / MANIFEST_NAME).is_file():
        raise ExportTargetError(f"{out} : dossier non vide sans {MANIFEST_NAME} (pas un export)")


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _move(src: Path, dst: Path) -> None:
    os.replace(src, dst)


def replace_dir(out: Path, files: Mapping[str, bytes]) -> None:
    """Écrit `files` (chemins relatifs, séparateur `/`) dans un dossier temporaire voisin, puis
    remplace `out` par ce dossier (R2) : aucun fichier d'un export précédent ne subsiste.

    En cas d'échec, `out` reste dans son état antérieur (restauré s'il avait déjà été déplacé)
    et aucun dossier temporaire ne reste ; l'exception est propagée.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=out.parent, prefix=f".{out.name}.new-"))
    backup: Path | None = None
    try:
        for relative, content in files.items():
            _write_file(staging.joinpath(*relative.split("/")), content)
        if out.exists():
            backup = out.parent / f".{out.name}.old-{uuid.uuid4().hex}"
            _move(out, backup)
        _move(staging, out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        if backup is not None and backup.exists() and not out.exists():
            _move(backup, out)
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)


# --- Rendu et export complet (R1, R11, R15) ----------------------------------------------------

#: SHA git accepté par le manifest (abrégé ou complet).
_GIT_SHA: Final = re.compile(r"^[0-9a-f]{7,40}$")


def _env_sha(environ: Mapping[str, str], name: str) -> str | None:
    value = environ.get(name, "").strip().lower()
    return value if _GIT_SHA.match(value) else None


def _repo_head(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.strip().lower()
    return sha if _GIT_SHA.match(sha) else None


def resolve_git_sha(environ: Mapping[str, str], repo_root: Path) -> str | None:
    """`TH_GIT_SHA` s'il est valide, sinon `git rev-parse HEAD` dans `repo_root`, sinon
    `GITHUB_SHA` s'il est valide, sinon `None` (F08 R11, modifié par F10 R8).

    En CI, `GITHUB_SHA` désigne le commit déclencheur du run, pas forcément le commit de données
    déployé : il ne sert qu'en dernier recours, hors dépôt git.
    """
    return (
        _env_sha(environ, "TH_GIT_SHA") or _repo_head(repo_root) or _env_sha(environ, "GITHUB_SHA")
    )


def render_files(
    universe: UniverseConfig,
    sources: Sources,
    *,
    calendar: NyseCalendar,
    now: datetime,
    git_sha: str | None,
) -> dict[str, bytes]:
    """Tous les fichiers de l'export M1, rendus en octets ; le manifest en dernier, à partir des
    octets des autres fichiers (empreintes exactes, R11). Déterministe à entrées égales (R15)."""
    prices = sources.prices
    last_dates = {symbol: file.bars[-1][0] for symbol, file in prices.items()}
    data_as_of = compute_data_as_of(last_dates)
    markers = collect_markers(sources.signals, set(prices))
    files: dict[str, bytes] = {
        f"tickers/{symbol}.json": render(build_ticker(file, markers[symbol]))
        for symbol, file in prices.items()
    }
    files["overview.json"] = render(build_overview(prices, data_as_of))
    files["health.json"] = render(
        build_health(
            [symbol for symbol, _start in universe_targets(universe)],
            last_dates,
            sources.reports,
            session=calendar.last_closed_session(now),
            calendar=calendar,
        )
    )
    manifest = build_manifest(
        universe,
        prices,
        files,
        generated_at=now.astimezone(UTC).replace(microsecond=0),
        git_sha=git_sha,
        data_as_of=data_as_of,
    )
    files[MANIFEST_NAME] = render(manifest)
    return files


@dataclass(frozen=True)
class ExportOutcome:
    """Résultat de `th export`, pour le résumé affiché (R3)."""

    out: Path
    sizes: dict[str, int]  # chemin relatif → octets, manifest compris
    data_as_of: date | None


def export(
    universe: UniverseConfig,
    *,
    data_root: Path,
    out: Path,
    repo_root: Path,
    calendar: NyseCalendar,
    now: Callable[[], datetime],
    git_sha: str | None,
) -> ExportOutcome:
    """`th export` : vérifie `out` (`ExportTargetError`), lit les sources (`ExportSourceError`,
    rien n'est écrit), rend tous les fichiers en mémoire puis remplace `out` (R1, R2, R13)."""
    check_target(out, data_root=data_root, repo_root=repo_root)
    sources = read_sources(universe, data_root)
    files = render_files(universe, sources, calendar=calendar, now=now(), git_sha=git_sha)
    replace_dir(out, files)
    last_dates = {symbol: file.bars[-1][0] for symbol, file in sources.prices.items()}
    return ExportOutcome(
        out=out,
        sizes={path: len(content) for path, content in sorted(files.items())},
        data_as_of=compute_data_as_of(last_dates),
    )
