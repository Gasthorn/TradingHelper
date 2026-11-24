"""Orchestration de `th export` (F08) : lecture des sources, rendu, écriture du dossier.

Effets de bord fichiers isolés ici (CLAUDE.md) ; la construction des fichiers est pure
(`export/build.py`). Aucune écriture dans `data/` : l'export ne modifie aucune source (R1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ValidationError

from tradinghelper.config import UniverseConfig, universe_targets
from tradinghelper.data.storage import PricesFileError, prices_path, read_json, read_prices
from tradinghelper.schemas import HEALTH_RUNS, PricesFile, RunReport, SignalsFile

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
