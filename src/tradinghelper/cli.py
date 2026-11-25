"""CLI `th` : une commande par étape du pipeline."""

from __future__ import annotations

import os
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer

# Typer embarque sa copie de Click ; son Context de base n'a pas d'alias public.
from typer._click import Context as _ClickContext
from typer.core import TyperGroup

from tradinghelper import __version__
from tradinghelper.config import (
    AppConfig,
    ConfigError,
    find_repo_root,
    load_config,
    universe_targets,
)
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.ingest import IngestOutcome, IngestRequest
from tradinghelper.data.ingest import ingest as run_ingest
from tradinghelper.data.source import PriceSource, YFinanceSource
from tradinghelper.data.storage import (
    RunReportError,
    append_run_report_entry,
    data_dir,
    read_run_reports,
    run_report_path,
    update_run_report,
)
from tradinghelper.data.validate import ValidateOutcome, ValidateRequest
from tradinghelper.data.validate import validate as run_validate
from tradinghelper.export.dashboard import (
    ExportOutcome,
    ExportSourceError,
    ExportTargetError,
    resolve_git_sha,
)
from tradinghelper.export.dashboard import export as run_export
from tradinghelper.orchestration.commit_message import PREFIX, CommitKind, build_commit_message
from tradinghelper.schemas import ValidateViolation, write_json_schemas

# Commandes qui n'ont pas besoin d'une config valide.
CONFIG_EXEMPT_COMMANDS: frozenset[str] = frozenset({"schemas", "commit-message"})

HELP_FLAGS = frozenset({"--help", "-h"})

CONFIG_ERROR_EXIT_CODE = 2
USAGE_ERROR_EXIT_CODE = 2  # arguments invalides (F01 R13, R14)

_RAW_ARGS_KEY = "tradinghelper.raw_args"


class _Group(TyperGroup):
    """Conserve les arguments bruts : Click les consomme avant d'appeler le callback racine,
    qui doit pourtant savoir si `th <commande> --help` a été demandé."""

    def parse_args(self, ctx: _ClickContext, args: list[str]) -> list[str]:
        ctx.meta[_RAW_ARGS_KEY] = tuple(args)
        return super().parse_args(ctx, args)


app = typer.Typer(cls=_Group, no_args_is_help=True)


def _help_requested(ctx: typer.Context) -> bool:
    raw_args: tuple[str, ...] = ctx.meta.get(_RAW_ARGS_KEY, ())
    return not HELP_FLAGS.isdisjoint(raw_args)


@app.callback()
def main(ctx: typer.Context) -> None:
    """TradingHelper — pipeline de données et de stratégies."""
    if ctx.resilient_parsing or _help_requested(ctx):
        return
    if ctx.invoked_subcommand in CONFIG_EXEMPT_COMMANDS:
        return
    try:
        ctx.obj = load_config()
    except ConfigError as err:
        typer.echo(f"Erreur de configuration : {err}", err=True)
        raise typer.Exit(code=CONFIG_ERROR_EXIT_CODE) from None


@app.command()
def version() -> None:
    """Affiche la version du package."""
    typer.echo(f"tradinghelper {__version__}")


@app.command()
def schemas(
    out_dir: Annotated[
        Path | None,
        typer.Option(help="Dossier de sortie (défaut : schemas/ à la racine du dépôt)."),
    ] = None,
) -> None:
    """Génère les JSON Schemas des contrats de données depuis `schemas.py`."""
    target = out_dir if out_dir is not None else find_repo_root() / "schemas"
    for path in write_json_schemas(target):
        typer.echo(f"écrit : {path.as_posix()}")


# --- th ingest (F01) ---------------------------------------------------------------------------
# Points d'injection, remplacés dans les tests (R16) : aucun réseau, aucune attente réelle.


def _make_source() -> PriceSource:
    return YFinanceSource()


def _now() -> datetime:
    return datetime.now(UTC)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _usage_error(message: str) -> typer.Exit:
    typer.echo(f"Erreur : {message}", err=True)
    return typer.Exit(code=USAGE_ERROR_EXIT_CODE)


def _parse_symbols(config: AppConfig, symbols: str | None) -> tuple[str, ...] | None:
    """`--symbols A,B` : symboles de l'univers ou benchmark (F01 R13, F02 R5) ; sinon code 2."""
    if symbols is None:
        return None
    known = [symbol for symbol, _ in universe_targets(config.universe)]
    parts = [part.strip().upper() for part in symbols.split(",") if part.strip()]
    if not parts:
        raise _usage_error("--symbols ne contient aucun symbole")
    unknown = [part for part in parts if part not in known]
    if unknown:
        raise _usage_error(
            f"symbole(s) hors univers et hors benchmark : {', '.join(unknown)} "
            f"(connus : {', '.join(known)})"
        )
    return tuple(dict.fromkeys(parts))


def _parse_request(
    config: AppConfig, symbols: str | None, full: bool, start: str | None, today: date
) -> IngestRequest:
    """Valide les options de `th ingest` avant tout appel réseau (R13) ; sinon code 2."""
    selected = _parse_symbols(config, symbols)
    start_date: date | None = None
    if start is not None:
        if not full:
            raise _usage_error("--start n'a de sens qu'avec --full")
        try:
            start_date = date.fromisoformat(start)
        except ValueError:
            raise _usage_error(f"date --start invalide : {start!r} (attendu AAAA-MM-JJ)") from None
        if start_date > today:
            raise _usage_error(f"date --start {start_date.isoformat()} dans le futur")
    return IngestRequest(symbols=selected, full=full, start=start_date)


def _summary(outcome: IngestOutcome) -> list[str]:
    counts = {"ok": 0, "unchanged": 0, "failed": 0}
    for ticker in outcome.run.tickers:
        counts[ticker.status] += 1
    lines = [
        f"Séance {outcome.session.isoformat()} : {counts['ok']} mis à jour, "
        f"{counts['unchanged']} inchangés, {counts['failed']} en échec."
    ]
    lines += [f"  - {t.symbol} : {t.error}" for t in outcome.run.tickers if t.status == "failed"]
    rewritten = [t.symbol for t in outcome.run.tickers if t.history_rewritten]
    if rewritten:
        lines.append(f"Historique réécrit : {', '.join(rewritten)}")
    if outcome.run.warnings:
        lines.append(f"{len(outcome.run.warnings)} barre(s) écartée(s) ou signalée(s).")
    return lines


@app.command()
def ingest(
    ctx: typer.Context,
    symbols: Annotated[
        str | None,
        typer.Option(
            help="Symboles à traiter, séparés par des virgules (défaut : tout l'univers)."
        ),
    ] = None,
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help="Re-télécharge tout l'historique et REMPLACE le fichier depuis --start "
            "(un --start postérieur au début actuel tronque l'historique).",
        ),
    ] = False,
    start: Annotated[
        str | None,
        typer.Option(
            help="Début du backfill AAAA-MM-JJ (avec --full ; défaut : start de l'univers)."
        ),
    ] = None,
) -> None:
    """Télécharge les cours journaliers (yfinance) dans data/raw/prices/ et écrit le rapport."""
    config: AppConfig = ctx.obj
    started = _now()
    request = _parse_request(config, symbols, full, start, started.date())
    data_root = data_dir()
    outcome = run_ingest(
        config.universe,
        request,
        source=_make_source(),
        calendar=NyseCalendar(),
        now=_now,
        sleep=_sleep,
        data_root=data_root,
    )
    for line in _summary(outcome):
        typer.echo(line)
    if outcome.should_report:
        report = run_report_path(data_root, outcome.session)
        try:
            update_run_report(report, outcome.session, outcome.run)
        except RunReportError as err:
            # Les prix sont déjà écrits ; le rapport existant n'est jamais écrasé (P7).
            typer.echo(f"Erreur : rapport de run non écrit : {err}", err=True)
        else:
            typer.echo(f"Rapport : {report.as_posix()}")
    else:
        typer.echo("Rien à signaler : aucun rapport écrit.")
    raise typer.Exit(code=outcome.run.exit_code)


# --- th validate (F02) -------------------------------------------------------------------------


def _validate_summary(outcome: ValidateOutcome) -> list[str]:
    run = outcome.run
    lines = [
        f"Séance {outcome.session.isoformat()} : {run.files_checked} fichier(s) vérifié(s), "
        f"{len(run.violations)} violation(s), {len(run.warnings)} avertissement(s)."
    ]
    counts = Counter(w.rule for w in run.warnings)
    if counts:
        lines.append(
            "Avertissements : " + ", ".join(f"{rule}: {n}" for rule, n in sorted(counts.items()))
        )
    return lines


def _violation_line(violation: ValidateViolation) -> str:
    day = violation.date.isoformat() if violation.date is not None else "-"
    return f"{violation.symbol} {day} {violation.rule}: {violation.detail}"


@app.command()
def validate(
    ctx: typer.Context,
    symbols: Annotated[
        str | None,
        typer.Option(
            help="Symboles à valider, séparés par des virgules (défaut : tous les fichiers, "
            "y compris hors univers ; avec cette option, les fichiers non listés sont ignorés)."
        ),
    ] = None,
    all_history: Annotated[
        bool,
        typer.Option(
            "--all-history",
            help="Avertissements sur tout l'historique (défaut : les 10 dernières séances).",
        ),
    ] = False,
) -> None:
    """Valide les fichiers de prix de data/raw/prices/ (lecture seule).

    Code 1 si une règle bloquante est violée, 0 sinon (avertissements compris), 2 en cas
    d'erreur de configuration ou d'arguments.
    """
    config: AppConfig = ctx.obj
    request = ValidateRequest(symbols=_parse_symbols(config, symbols), all_history=all_history)
    data_root = data_dir()
    outcome = run_validate(
        config.universe, request, calendar=NyseCalendar(), now=_now, data_root=data_root
    )
    for violation in outcome.run.violations:
        typer.echo(_violation_line(violation), err=True)
    for line in _validate_summary(outcome):
        typer.echo(line)
    # R7 : rapport écrit s'il existe déjà pour S (le daily l'a ouvert) ou s'il y a une violation ;
    # sinon (jour férié, 2e run) rien n'est écrit, pour ne pas créer de commit. Toujours avant
    # la sortie, y compris en code 1 (téléversé par F10 R4).
    report = run_report_path(data_root, outcome.session)
    if report.exists() or outcome.has_violations:
        try:
            append_run_report_entry(report, outcome.session, "validate", outcome.run)
        except RunReportError as err:
            # Rapport existant jamais écrasé (P7) ; code de sortie de la validation inchangé.
            typer.echo(f"Erreur : rapport de run non écrit : {err}", err=True)
        else:
            typer.echo(f"Rapport : {report.as_posix()}")
    else:
        typer.echo("Rien à signaler : aucun rapport écrit.")
    raise typer.Exit(code=outcome.run.exit_code)


# --- th export (F08) ---------------------------------------------------------------------------

DEFAULT_EXPORT_DIR = Path("dashboard") / "public" / "data"


def _git_sha() -> str | None:
    """Point d'injection (tests) : SHA git journalisé dans le manifest (R11)."""
    return resolve_git_sha(os.environ, find_repo_root())


def _kilobytes(size: int) -> str:
    return f"{size / 1024:.1f} Ko"


def _export_summary(outcome: ExportOutcome) -> list[str]:
    total = sum(outcome.sizes.values())
    biggest = max(outcome.sizes, key=lambda path: outcome.sizes[path])
    as_of = outcome.data_as_of.isoformat() if outcome.data_as_of else "aucune donnée de prix"
    return [
        f"Export : {len(outcome.sizes)} fichier(s), {_kilobytes(total)} dans "
        f"{outcome.out.as_posix()}",
        f"Plus gros fichier : {biggest} ({_kilobytes(outcome.sizes[biggest])})",
        f"Données à jour au : {as_of}",
    ]


@app.command()
def export(
    ctx: typer.Context,
    out: Annotated[
        Path | None,
        typer.Option(
            help="Dossier de sortie, reconstruit entièrement "
            "(défaut : dashboard/public/data à la racine du dépôt)."
        ),
    ] = None,
) -> None:
    """Exporte les données pour le dashboard (JSON minifiés, contrat §7).

    Lecture seule sur data/. Code 1 si un fichier source est illisible ou hors contrat (rien
    n'est écrit), 2 en cas d'erreur de configuration ou d'un dossier de sortie refusé.
    """
    config: AppConfig = ctx.obj
    repo_root = find_repo_root()
    target = out if out is not None else repo_root / DEFAULT_EXPORT_DIR
    try:
        outcome = run_export(
            config.universe,
            data_root=data_dir(),
            out=target,
            repo_root=repo_root,
            calendar=NyseCalendar(),
            now=_now,
            git_sha=_git_sha(),
        )
    except ExportTargetError as err:
        raise _usage_error(f"dossier de sortie refusé : {err}") from None
    except ExportSourceError as err:
        for problem in err.problems:
            typer.echo(str(problem), err=True)
        typer.echo(
            f"Export annulé : {len(err.problems)} source(s) invalide(s), aucun fichier écrit.",
            err=True,
        )
        raise typer.Exit(code=1) from None
    for line in _export_summary(outcome):
        typer.echo(line)


# --- th commit-message (F10) -------------------------------------------------------------------


def _parse_since(value: str) -> datetime:
    """`--since` : horodatage ISO-8601 avec fuseau (`Z` accepté), converti en UTC ; sinon code 2."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise _usage_error(f"--since invalide : {value!r} (ISO-8601 attendu)") from None
    if parsed.tzinfo is None:
        raise _usage_error(f"--since sans fuseau horaire : {value!r} (ex. 2026-11-24T22:30:00Z)")
    return parsed.astimezone(UTC)


def _parse_kind(value: str) -> CommitKind:
    for kind in PREFIX:
        if kind == value:
            return kind
    raise _usage_error(f"--kind inconnu : {value!r} (attendu : {', '.join(PREFIX)})")


@app.command("commit-message")
def commit_message(
    kind: Annotated[str, typer.Option(help="Type de commit : daily, backfill ou model.")],
    since: Annotated[
        str,
        typer.Option(help="Début du run (T0), ISO-8601 avec fuseau, ex. 2026-11-24T22:30:00Z."),
    ],
) -> None:
    """Affiche le message de commit des données du run démarré à --since (F10 R5).

    Journalise les réécritures d'historique des exécutions `th ingest` démarrées depuis T0
    (P5). Lecture seule, sans réseau ni configuration. Code 1 si un rapport de run est
    illisible ou hors contrat, 2 si un argument est invalide.
    """
    commit_kind = _parse_kind(kind)
    started = _parse_since(since)
    try:
        reports = read_run_reports(data_dir() / "runs")
    except RunReportError as err:
        typer.echo(f"Rapport de run invalide : {err}", err=True)
        raise typer.Exit(code=1) from None
    session = NyseCalendar().last_closed_session(_now())
    typer.echo(build_commit_message(commit_kind, reports, since=started, fallback_session=session))
