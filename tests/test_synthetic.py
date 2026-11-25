"""Tests du générateur de prix synthétiques utilisé par les tests de volume (F08 — R19)."""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from synthetic import synthetic_bars, write_synthetic_prices
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.quality import check_rows
from tradinghelper.data.storage import dumps_prices, read_prices

CAL = NyseCalendar()
S = date(2026, 11, 24)
SESSIONS = CAL.sessions(date(2026, 1, 2), S)


def test_generated_files_are_valid_prices(tmp_path: Path) -> None:
    """Fichiers conformes au contrat §2, sans violation F02, en sérialisation canonique."""
    paths = write_synthetic_prices(
        tmp_path, ["AAPL", "BRK.B", "SPY"], SESSIONS, np.random.default_rng(1)
    )

    assert sorted(paths) == ["AAPL", "BRK.B", "SPY"]
    for symbol, path in paths.items():
        assert path == tmp_path / f"{symbol}.json"
        prices = read_prices(path)
        assert prices is not None
        assert prices.symbol == symbol
        assert path.read_text(encoding="utf-8") == dumps_prices(prices)
        rows = json.loads(path.read_text(encoding="utf-8"))["bars"]
        check = check_rows(symbol, rows, last_session=S, is_session=CAL.is_session)
        assert check.violations == []


def test_same_seed_same_bytes(tmp_path: Path) -> None:
    first = write_synthetic_prices(tmp_path / "a", ["AAPL"], SESSIONS, np.random.default_rng(42))
    second = write_synthetic_prices(tmp_path / "b", ["AAPL"], SESSIONS, np.random.default_rng(42))
    other = write_synthetic_prices(tmp_path / "c", ["AAPL"], SESSIONS, np.random.default_rng(43))

    assert first["AAPL"].read_bytes() == second["AAPL"].read_bytes()
    assert first["AAPL"].read_bytes() != other["AAPL"].read_bytes()


def test_dates_are_nyse_sessions() -> None:
    bars = synthetic_bars(SESSIONS, np.random.default_rng(3))

    assert [bar[0] for bar in bars] == SESSIONS


def test_prices_use_four_decimals() -> None:
    """Pire cas pour les tailles (R19) : la plupart des prix ont 4 décimales."""
    bars = synthetic_bars(SESSIONS, np.random.default_rng(5))

    closes = [bar[4] for bar in bars]
    four_decimals = [c for c in closes if round(c, 3) != c]
    assert len(four_decimals) > 0.8 * len(closes)


def test_empty_sessions() -> None:
    assert synthetic_bars([], np.random.default_rng(0)) == []


@pytest.mark.parametrize("n_symbols", [21])
def test_volume_generation_is_fast(tmp_path: Path, n_symbols: int) -> None:
    """21 symboles sur 15 ans (≈ 3 780 séances) en moins de 5 s."""
    sessions = CAL.sessions(date(2011, 11, 25), S)
    symbols = [f"T{i:02d}" for i in range(n_symbols)]

    started = time.perf_counter()
    paths = write_synthetic_prices(tmp_path, symbols, sessions, np.random.default_rng(7))
    elapsed = time.perf_counter() - started

    assert len(paths) == n_symbols
    assert len(sessions) > 3_700
    assert elapsed < 5.0, f"{elapsed:.1f} s"
