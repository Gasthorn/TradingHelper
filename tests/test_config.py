"""Tests du chargement de la configuration (F00 — R6 à R9)."""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tradinghelper.config import (
    AppConfig,
    ConfigError,
    UniverseConfig,
    _read_yaml,
    _validate,
    find_repo_root,
    load_config,
    resolve_config_dir,
)

from conftest import TODAY, VALID_BACKTEST, VALID_UNIVERSE, WriteConfig

REPO_ROOT = Path(__file__).resolve().parents[1]

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


# --- load_config : fichiers par défaut (R6) -----------------------------------------------------


def test_default_config_loads() -> None:
    config = load_config(REPO_ROOT / "config", today=TODAY)

    assert isinstance(config, AppConfig)
    assert config.config_dir == REPO_ROOT / "config"
    assert config.universe.currency == "USD"
    assert config.universe.benchmark == "SPY"
    symbols = [t.symbol for t in config.universe.tickers]
    assert len(symbols) == 20
    assert "SPY" not in symbols  # benchmark hors univers de trading (Q3)
    assert len({t.sector for t in config.universe.tickers}) >= 8  # Q2
    assert config.backtest.initial_capital == 10000.0
    assert config.strategies.strategies == []


def test_load_config_from_written_dir(write_config: WriteConfig) -> None:
    config_dir = write_config()

    config = load_config(config_dir, today=TODAY)

    assert config.config_dir == config_dir
    assert [t.symbol for t in config.universe.tickers] == ["AAPL", "MSFT", "BRK-B"]
    assert config.backtest.slippage_bps == 5


@pytest.mark.parametrize("stem", ["universe", "backtest", "strategies"])
def test_missing_file_names_it(write_config: WriteConfig, stem: str) -> None:
    config_dir = write_config()
    (config_dir / f"{stem}.yaml").unlink()

    with pytest.raises(ConfigError) as excinfo:
        load_config(config_dir, today=TODAY)

    assert excinfo.value.file == config_dir / f"{stem}.yaml"


# --- BacktestConfig (R8) ------------------------------------------------------------------------


def _backtest(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(VALID_BACKTEST)
    data.update(changes)
    return data


@pytest.mark.parametrize(
    ("data", "expected_field"),
    [
        (_backtest(initial_capital=0), "initial_capital"),
        (_backtest(initial_capital=-100.0), "initial_capital"),
        (_backtest(commission_fixed=-1.0), "commission_fixed"),
        (_backtest(commission_pct=-0.001), "commission_pct"),
        (_backtest(slippage_bps=-5), "slippage_bps"),
        (_backtest(leverage=2), "leverage"),
    ],
    ids=[
        "capital-nul",
        "capital-negatif",
        "commission-fixe-negative",
        "commission-pct-negative",
        "slippage-negatif",
        "cle-inconnue",
    ],
)
def test_invalid_backtest(
    write_config: WriteConfig, data: dict[str, Any], expected_field: str
) -> None:
    config_dir = write_config(backtest=data)

    with pytest.raises(ConfigError) as excinfo:
        load_config(config_dir, today=TODAY)

    assert excinfo.value.file == config_dir / "backtest.yaml"
    assert excinfo.value.field == expected_field


# --- StrategiesConfig (R8) ----------------------------------------------------------------------


def test_strategy_entry_defaults(write_config: WriteConfig) -> None:
    config_dir = write_config(strategies={"strategies": [{"id": "buy_hold", "type": "buy_hold"}]})

    entry = load_config(config_dir, today=TODAY).strategies.strategies[0]

    assert entry.id == "buy_hold"
    assert entry.active is True
    assert entry.params == {}


def test_duplicate_strategy_id(write_config: WriteConfig) -> None:
    strategies = {
        "strategies": [
            {"id": "sma_cross", "type": "sma_cross", "params": {"fast": 20, "slow": 50}},
            {"id": "sma_cross", "type": "sma_cross", "params": {"fast": 10, "slow": 30}},
        ]
    }
    config_dir = write_config(strategies=strategies)

    with pytest.raises(ConfigError, match="sma_cross") as excinfo:
        load_config(config_dir, today=TODAY)

    assert excinfo.value.file == config_dir / "strategies.yaml"
    assert excinfo.value.field == "strategies"


def test_unknown_strategy_key(write_config: WriteConfig) -> None:
    strategies = {"strategies": [{"id": "x", "type": "buy_hold", "enabled": True}]}
    config_dir = write_config(strategies=strategies)

    with pytest.raises(ConfigError) as excinfo:
        load_config(config_dir, today=TODAY)

    assert excinfo.value.field == "strategies[0].enabled"


# --- Résolution du dossier de config (R7) -------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Faux dépôt : pyproject.toml à la racine, sous-dossier dashboard/src."""
    repo = tmp_path / "repo"
    (repo / "dashboard" / "src").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    return repo


def test_resolve_explicit_arg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TH_CONFIG_DIR", str(tmp_path / "from-env"))

    assert resolve_config_dir(tmp_path / "explicit") == tmp_path / "explicit"


def test_resolve_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TH_CONFIG_DIR", str(tmp_path / "from-env"))

    assert resolve_config_dir() == tmp_path / "from-env"


def test_resolve_empty_env_var_is_ignored(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TH_CONFIG_DIR", "")
    monkeypatch.chdir(fake_repo)

    assert resolve_config_dir() == fake_repo.resolve() / "config"


def test_resolve_from_subdirectory(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TH_CONFIG_DIR", raising=False)
    monkeypatch.chdir(fake_repo / "dashboard" / "src")

    assert resolve_config_dir() == fake_repo.resolve() / "config"


def test_find_repo_root_from_explicit_start(fake_repo: Path) -> None:
    assert find_repo_root(fake_repo / "dashboard") == fake_repo.resolve()


def test_no_repo_root_raises(tmp_path: Path) -> None:
    orphan = tmp_path / "orphan"
    orphan.mkdir()
    if any((parent / "pyproject.toml").is_file() for parent in [orphan, *orphan.parents]):
        pytest.skip("un pyproject.toml existe au-dessus du dossier temporaire")

    with pytest.raises(ConfigError, match=r"pyproject\.toml"):
        find_repo_root(orphan)


def test_load_config_without_arg_uses_repo_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TH_CONFIG_DIR", raising=False)
    monkeypatch.chdir(REPO_ROOT / "tests")

    config = load_config(today=TODAY)

    assert config.config_dir == REPO_ROOT / "config"
