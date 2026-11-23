"""Fixtures partagées : jeu de configuration valide, modifiable par test."""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

# Date du jour figée pour les tests (la validation de `start` en dépend).
TODAY = date(2026, 11, 23)

VALID_UNIVERSE: dict[str, Any] = {
    "currency": "USD",
    "benchmark": "SPY",
    "tickers": [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "sector": "Information Technology",
            "start": date(2010, 1, 1),
        },
        {
            "symbol": "MSFT",
            "name": "Microsoft",
            "sector": "Information Technology",
            "start": date(2010, 1, 1),
        },
        {
            "symbol": "BRK-B",
            "name": "Berkshire Hathaway",
            "sector": "Financials",
            "start": date(2010, 1, 1),
        },
    ],
}

VALID_BACKTEST: dict[str, Any] = {
    "initial_capital": 10000.0,
    "commission_fixed": 1.0,
    "commission_pct": 0.0,
    "slippage_bps": 5,
}

VALID_STRATEGIES: dict[str, Any] = {"strategies": []}

WriteConfig = Callable[..., Path]


def dump_yaml(path: Path, data: object) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def write_config(tmp_path: Path) -> WriteConfig:
    """Écrit un `config/` valide ; `universe=`, `backtest=`, `strategies=` le modifient."""

    def _write(**overrides: object) -> Path:
        files: dict[str, object] = {
            "universe": copy.deepcopy(VALID_UNIVERSE),
            "backtest": copy.deepcopy(VALID_BACKTEST),
            "strategies": copy.deepcopy(VALID_STRATEGIES),
        }
        unknown = set(overrides) - set(files)
        if unknown:
            raise ValueError(f"fichiers de config inconnus : {sorted(unknown)}")
        files.update(overrides)
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        for stem, data in files.items():
            dump_yaml(config_dir / f"{stem}.yaml", data)
        return config_dir

    return _write
