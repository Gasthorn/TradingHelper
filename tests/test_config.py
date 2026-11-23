"""Tests du chargement de la configuration (F00 — R6 à R9)."""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tradinghelper.config import ConfigError, UniverseConfig, _read_yaml, _validate

from conftest import TODAY, VALID_UNIVERSE, WriteConfig

# --- ConfigError ---------------------------------------------------------------------------------


def test_config_error_message_with_field() -> None:
    err = ConfigError(Path("config/universe.yaml"), "tickers[3].symbol", "symbole dupliqué 'AAPL'")

    assert str(err) == "config/universe.yaml: tickers[3].symbol: symbole dupliqué 'AAPL'"
    assert err.file == Path("config/universe.yaml")
    assert err.field == "tickers[3].symbol"
    assert err.reason == "symbole dupliqué 'AAPL'"


def test_config_error_message_without_field() -> None:
    err = ConfigError(Path("config/backtest.yaml"), None, "fichier introuvable")

    assert str(err) == "config/backtest.yaml: fichier introuvable"


# --- _read_yaml (R8 : erreurs de lecture) --------------------------------------------------------


def test_read_yaml_returns_mapping(tmp_path: Path) -> None:
    path = tmp_path / "ok.yaml"
    path.write_text("currency: USD\ntickers:\n  - symbol: AAPL\n", encoding="utf-8")

    assert _read_yaml(path) == {"currency": "USD", "tickers": [{"symbol": "AAPL"}]}


@pytest.mark.parametrize(
    ("content", "expected_reason"),
    [
        (None, "introuvable"),
        ("", "vide"),
        ("# seulement un commentaire\n", "vide"),
        ("currency: [USD\n", "YAML invalide"),
        ("currency: USD\ncurrency: EUR\n", "clé dupliquée"),
        ("- AAPL\n- MSFT\n", "mapping"),
        ("USD\n", "mapping"),
    ],
    ids=[
        "absent",
        "vide",
        "commentaire-seul",
        "mal-forme",
        "cle-dupliquee",
        "racine-liste",
        "racine-scalaire",
    ],
)
def test_read_yaml_errors(tmp_path: Path, content: str | None, expected_reason: str) -> None:
    path = tmp_path / "universe.yaml"
    if content is not None:
        path.write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        _read_yaml(path)

    assert excinfo.value.file == path
    assert path.as_posix() in str(excinfo.value)
    assert expected_reason in excinfo.value.reason


def test_read_yaml_duplicate_key_names_field(tmp_path: Path) -> None:
    path = tmp_path / "backtest.yaml"
    path.write_text("initial_capital: 1\nslippage_bps: 5\nslippage_bps: 6\n", encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        _read_yaml(path)

    assert excinfo.value.field == "slippage_bps"


# --- UniverseConfig (R6, R8) ----------------------------------------------------------------------


def _load_universe(config_dir: Path, today: date = TODAY) -> UniverseConfig:
    path = config_dir / "universe.yaml"
    return _validate(UniverseConfig, _read_yaml(path), path, today)


def _universe(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(VALID_UNIVERSE)
    data.update(changes)
    return data


def _universe_ticker(index: int, **changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(VALID_UNIVERSE)
    data["tickers"][index].update(changes)
    return data


def _universe_without(index: int, key: str) -> dict[str, Any]:
    data = copy.deepcopy(VALID_UNIVERSE)
    del data["tickers"][index][key]
    return data


def test_valid_universe_loads(write_config: WriteConfig) -> None:
    universe = _load_universe(write_config())

    assert universe.currency == "USD"
    assert universe.benchmark == "SPY"
    assert [t.symbol for t in universe.tickers] == ["AAPL", "MSFT", "BRK-B"]
    assert universe.tickers[0].start == date(2010, 1, 1)


def test_universe_start_today_is_accepted(write_config: WriteConfig) -> None:
    universe = _load_universe(write_config(universe=_universe_ticker(0, start=TODAY)))

    assert universe.tickers[0].start == TODAY


INVALID_UNIVERSES: list[tuple[str, Callable[[], dict[str, Any]], str]] = [
    ("cle-inconnue", lambda: _universe(exchange="NYSE"), "exchange"),
    ("cle-inconnue-ticker", lambda: _universe_ticker(0, isin="US0378331005"), "tickers[0].isin"),
    ("champ-manquant", lambda: _universe_without(0, "name"), "tickers[0].name"),
    ("tickers-vide", lambda: _universe(tickers=[]), "tickers"),
    ("symbole-duplique", lambda: _universe_ticker(2, symbol="AAPL"), "tickers"),
    ("symbole-minuscules", lambda: _universe_ticker(1, symbol="msft"), "tickers[1].symbol"),
    ("symbole-trop-long", lambda: _universe_ticker(1, symbol="ABCDEFGHIJK"), "tickers[1].symbol"),
    ("benchmark-invalide", lambda: _universe(benchmark="s&p"), "benchmark"),
    ("start-invalide", lambda: _universe_ticker(0, start="2010-13-45"), "tickers[0].start"),
    ("start-future", lambda: _universe_ticker(0, start=date(2026, 11, 24)), "tickers[0].start"),
    ("devise-eur", lambda: _universe(currency="EUR"), "currency"),
]


@pytest.mark.parametrize(
    ("make_data", "expected_field"),
    [(make, field) for _, make, field in INVALID_UNIVERSES],
    ids=[case_id for case_id, _, _ in INVALID_UNIVERSES],
)
def test_invalid_universe(
    write_config: WriteConfig, make_data: Callable[[], dict[str, Any]], expected_field: str
) -> None:
    config_dir = write_config(universe=make_data())
    path = config_dir / "universe.yaml"

    with pytest.raises(ConfigError) as excinfo:
        _load_universe(config_dir)

    err = excinfo.value
    assert err.file == path
    assert err.field == expected_field
    assert path.as_posix() in str(err)
    assert f": {expected_field}: " in str(err)
    assert err.reason


def test_duplicate_symbol_reason_names_symbol(write_config: WriteConfig) -> None:
    config_dir = write_config(universe=_universe_ticker(2, symbol="AAPL"))

    with pytest.raises(ConfigError, match="AAPL"):
        _load_universe(config_dir)
