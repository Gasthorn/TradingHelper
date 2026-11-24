"""Orchestration de `th validate` (F02) : lecture des fichiers de prix (via `storage`),
application des règles pures de `quality`, assemblage du résultat.

Lecture seule : aucune fonction d'écriture de prix n'est appelée ici (R5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from pydantic import JsonValue, ValidationError

from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.quality import (
    STALE_SESSIONS,
    check_rows,
    large_moves,
    missing_sessions,
    stale,
    zero_volumes,
)
from tradinghelper.data.storage import PricesFileError, read_json
from tradinghelper.schemas import (
    Bar,
    BlockingRule,
    PricesFile,
    ValidateViolation,
    ValidateWarning,
)


@dataclass(frozen=True)
class FileResult:
    """Violations et avertissements d'un fichier de prix."""

    violations: list[ValidateViolation] = field(default_factory=list)
    warnings: list[ValidateWarning] = field(default_factory=list)


def _errors(exc: ValidationError) -> list[str]:
    """Messages `champ: raison` d'une erreur pydantic, un par erreur."""
    messages: list[str] = []
    for error in exc.errors(include_url=False):
        location = ".".join(str(part) for part in error["loc"]) or "fichier"
        messages.append(f"{location}: {str(error['msg']).removeprefix('Value error, ')}")
    return messages


def _check_header(data: JsonValue) -> list[str]:
    """Erreurs de l'en-tête (tout sauf le contenu de `bars`) au regard de `PricesFile`.

    L'en-tête est validé avec `bars` vide : le contrat reste la seule définition des clés.
    """
    if not isinstance(data, dict):
        return [f"fichier : objet JSON attendu, reçu {type(data).__name__}"]
    header = dict(data)
    if "bars" in header:
        if not isinstance(header["bars"], list):
            return [f"bars : liste attendue, reçu {type(header['bars']).__name__}"]
        header["bars"] = []
    try:
        PricesFile.model_validate(header)
    except ValidationError as exc:
        return _errors(exc)
    return []


def _warnings(
    symbol: str,
    bars: list[Bar],
    *,
    session: date,
    recent_start: date,
    calendar: NyseCalendar,
    all_history: bool,
) -> list[ValidateWarning]:
    """Avertissements R3 d'un fichier conforme : stale, puis séances manquantes, sauts, volumes."""
    first, last = bars[0][0], bars[-1][0]
    since = first if all_history else max(first, recent_start)
    warnings: list[ValidateWarning] = []
    late = calendar.sessions(last + timedelta(days=1), session)
    stale_warning = stale(
        symbol,
        last,
        threshold=calendar.shift(session, -STALE_SESSIONS),
        sessions_late=len(late),
    )
    if stale_warning is not None:
        warnings.append(stale_warning)
    warnings += missing_sessions(symbol, bars, calendar.sessions(since, last))
    warnings += large_moves(symbol, bars, since=since)
    warnings += zero_volumes(symbol, bars, since=since)
    return warnings


def validate_file(
    symbol: str,
    path: Path,
    *,
    session: date,
    recent_start: date,
    calendar: NyseCalendar,
    in_universe: bool,
    all_history: bool,
) -> FileResult:
    """Valide un fichier de prix (F02 R1, R2) puis, s'il est conforme et que son symbole est dans
    l'univers, calcule ses avertissements (R3 ; R4 pour les orphelins).

    `symbol` : nom du fichier sans `.json`. `recent_start` : début de la fenêtre récente.
    """
    violations: list[ValidateViolation] = []

    def report(rule: BlockingRule, detail: str, day: date | None = None) -> None:
        violations.append(ValidateViolation(symbol=symbol, date=day, rule=rule, detail=detail))

    try:
        data = read_json(path)
    except (PricesFileError, FileNotFoundError) as exc:
        reason = exc.reason if isinstance(exc, PricesFileError) else "fichier introuvable"
        report("unreadable", reason)
        return FileResult(violations=violations)

    for message in _check_header(data):
        report("schema", message)
    if not isinstance(data, dict):
        return FileResult(violations=violations)

    declared = data.get("symbol")
    if isinstance(declared, str) and declared != symbol:
        report("symbol_mismatch", f"symbole {declared!r} dans le fichier {path.name!r}")

    rows = data.get("bars")
    bars: list[Bar] = []
    if isinstance(rows, list):
        checked = check_rows(symbol, rows, last_session=session, is_session=calendar.is_session)
        violations += checked.violations
        bars = checked.bars

    if not violations:
        # Filet de sécurité : le fichier doit être accepté par le contrat lui-même (R1).
        try:
            PricesFile.model_validate(data)
        except ValidationError as exc:
            for message in _errors(exc):
                report("schema", message)

    if violations or not in_universe or not bars:
        return FileResult(violations=violations)
    return FileResult(
        warnings=_warnings(
            symbol,
            bars,
            session=session,
            recent_start=recent_start,
            calendar=calendar,
            all_history=all_history,
        )
    )
