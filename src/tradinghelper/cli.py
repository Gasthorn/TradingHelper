"""CLI `th` : une commande par étape du pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

# Typer embarque sa copie de Click ; son Context de base n'a pas d'alias public.
from typer._click import Context as _ClickContext
from typer.core import TyperGroup

from tradinghelper import __version__
from tradinghelper.config import ConfigError, find_repo_root, load_config
from tradinghelper.schemas import write_json_schemas

# Commandes qui n'ont pas besoin d'une config valide.
CONFIG_EXEMPT_COMMANDS: frozenset[str] = frozenset({"schemas"})

HELP_FLAGS = frozenset({"--help", "-h"})

CONFIG_ERROR_EXIT_CODE = 2

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
