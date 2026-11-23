"""Tests du chargement de la configuration (F00 — R6 à R9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tradinghelper.config import ConfigError, _read_yaml

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
