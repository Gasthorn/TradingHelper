"""Fixtures d'export du dashboard (spec F09 — R24), commitées dans `dashboard/tests/fixtures/`.

Chaque jeu est rendu par l'export de F08 (`render_files`, pur) à partir de données figées :
prix synthétiques seedés, rapports de run et signaux de `tests/fixtures/export/`, horloge et
`git_sha` figés. Même code → mêmes octets ; `tests/test_dashboard_fixtures.py` le vérifie.

- `empty` : univers sans aucun fichier de prix (`data_as_of: null`, premier run) ;
- `m1` : AAPL (300 séances, dates des signaux incluses), BRK.B (150 séances : `sma200`
  entièrement nulle, symbole à point), NVDA (cours sous 1 $), SPY (benchmark), rapports de run ;
- `m1-signals` : `m1` + signaux (BUY le 2026-11-20 et SELL le 2026-11-23 sur AAPL).

Régénération : `uv run python tests/dashboard_fixtures.py` (`--check` : code 1 si périmé).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import numpy as np

from synthetic import synthetic_prices
from tradinghelper.config import UniverseConfig
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.export.dashboard import Sources, render_files, replace_dir
from tradinghelper.schemas import PricesFile, RunReport, SignalsFile

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
FIXTURES_DIR: Final = REPO_ROOT / "dashboard" / "tests" / "fixtures"
SOURCES_DIR: Final = Path(__file__).resolve().parent / "fixtures" / "export"
FIXTURE_NAMES: Final = ("empty", "m1", "m1-signals")
REGENERATE: Final = "régénérer avec `uv run python tests/dashboard_fixtures.py`"

FROZEN_NOW: Final = datetime(2026, 11, 23, 22, 50, tzinfo=UTC)  # après la clôture : S = 2026-11-23
FROZEN_SHA: Final = "0" * 40
LAST_SESSION: Final = date(2026, 11, 23)
SEED: Final = 9

#: Symbole → (nombre de séances, premier cours ; `None` = tiré par le générateur).
PRICE_PLAN: Final[dict[str, tuple[int, float | None]]] = {
    "AAPL": (300, None),
    "BRK.B": (150, None),
    "NVDA": (300, 0.12),
    "SPY": (300, None),
}


def fixture_universe() -> UniverseConfig:
    return UniverseConfig.model_validate(
        {
            "currency": "USD",
            "benchmark": "SPY",
            "tickers": [
                {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Information Technology",
                 "start": "2010-01-01"},
                {"symbol": "BRK.B", "name": "Berkshire Hathaway Inc. (Class B)",
                 "sector": "Financials", "start": "2010-01-01"},
                {"symbol": "NVDA", "name": "NVIDIA Corp.", "sector": "Information Technology",
                 "start": "2010-01-01"},
            ],
        }
    )  # fmt: skip


def _prices(calendar: NyseCalendar) -> dict[str, PricesFile]:
    """Prix synthétiques, dans l'ordre de l'univers puis le benchmark, avec un seul générateur."""
    rng = np.random.default_rng(SEED)
    prices: dict[str, PricesFile] = {}
    for symbol, (count, start) in PRICE_PLAN.items():
        sessions = calendar.sessions(calendar.shift(LAST_SESSION, -(count - 1)), LAST_SESSION)
        prices[symbol] = synthetic_prices(symbol, sessions, rng, start=start)
    return prices


def _reports() -> list[RunReport]:
    reports = (
        RunReport.model_validate_json(p.read_bytes()) for p in (SOURCES_DIR / "runs").glob("*.json")
    )
    return sorted(reports, key=lambda report: report.session_date, reverse=True)


def _signals() -> list[SignalsFile]:
    files = (
        SignalsFile.model_validate_json(p.read_bytes())
        for p in (SOURCES_DIR / "signals").glob("2*.json")
    )
    return sorted(files, key=lambda file: file.date)


def render_fixture(name: str) -> dict[str, bytes]:
    """Fichiers d'export du jeu `name`, rendus en mémoire."""
    calendar = NyseCalendar()
    if name == "empty":
        sources = Sources(prices={}, reports=[], signals=[])
    elif name == "m1":
        sources = Sources(prices=_prices(calendar), reports=_reports(), signals=[])
    elif name == "m1-signals":
        sources = Sources(prices=_prices(calendar), reports=_reports(), signals=_signals())
    else:
        raise ValueError(f"fixture inconnue : {name}")
    return render_files(
        fixture_universe(), sources, calendar=calendar, now=FROZEN_NOW, git_sha=FROZEN_SHA
    )


def build_fixture(name: str, out: Path) -> None:
    """Écrit le jeu `name` dans `out`, reconstruit entièrement (aucun fichier obsolète)."""
    replace_dir(out, render_fixture(name))


def _snapshot(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixtures d'export du dashboard (F09 R24).")
    parser.add_argument(
        "--check", action="store_true", help="vérifier sans écrire (code 1 si périmé)"
    )
    args = parser.parse_args(argv)

    stale: list[str] = []
    for name in FIXTURE_NAMES:
        target = FIXTURES_DIR / name
        if args.check:
            with tempfile.TemporaryDirectory() as tmp:
                build_fixture(name, Path(tmp) / name)
                if _snapshot(Path(tmp) / name) != _snapshot(target):
                    stale.append(name)
        else:
            build_fixture(name, target)
            where = target.relative_to(REPO_ROOT).as_posix()
            print(f"{name} : {len(_snapshot(target))} fichiers dans {where}")
    if stale:
        print(f"fixtures périmées : {', '.join(stale)} ; {REGENERATE}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
