"""CLI `th` : une commande par étape du pipeline."""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer

# Typer embarque sa copie de Click ; son Context de base n'a pas d'alias public.
from typer._click import Context as _ClickContext
from typer.core import TyperGroup

from tradinghelper import __version__
from tradinghelper.config import AppConfig, ConfigError, find_repo_root, load_config
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.ingest import IngestOutcome, IngestRequest
from tradinghelper.data.ingest import ingest as run_ingest
from tradinghelper.data.source import PriceSource, YFinanceSource
from tradinghelper.data.storage import (
    RunReportError,
    data_dir,
    run_report_path,
    update_run_report,
)
from tradinghelper.schemas import write_json_schemas

# Commandes qui n'ont pas besoin d'une config valide.
CONFIG_EXEMPT_COMMANDS: frozenset[str] = frozenset({"schemas"})

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


def _parse_request(
    config: AppConfig, symbols: str | None, full: bool, start: str | None, today: date
) -> IngestRequest:
    """Valide les options de `th ingest` avant tout appel réseau (R13) ; sinon code 2."""
    known = [t.symbol for t in config.universe.tickers] + [config.universe.benchmark]
    selected: tuple[str, ...] | None = None
    if symbols is not None:
        parts = [part.strip().upper() for part in symbols.split(",") if part.strip()]
        if not parts:
            raise _usage_error("--symbols ne contient aucun symbole")
        unknown = [part for part in parts if part not in known]
        if unknown:
            raise _usage_error(
                f"symbole(s) hors univers et hors benchmark : {', '.join(unknown)} "
                f"(connus : {', '.join(known)})"
            )
        selected = tuple(dict.fromkeys(parts))
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
