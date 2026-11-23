"""CLI `th` : une commande par étape du pipeline."""

from __future__ import annotations

import typer

from tradinghelper import __version__

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """TradingHelper — pipeline de données et de stratégies."""


@app.command()
def version() -> None:
    """Affiche la version du package."""
    typer.echo(f"tradinghelper {__version__}")
