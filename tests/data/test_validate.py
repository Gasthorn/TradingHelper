"""Tests de l'orchestration de `th validate` (F02 — R1 à R6)."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from tradinghelper.config import UniverseConfig
from tradinghelper.data import validate as validate_mod
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.quality import RECENT_SESSIONS, RowCheck
from tradinghelper.data.storage import dumps_prices
from tradinghelper.data.validate import (
    FileResult,
    ValidateOutcome,
    ValidateRequest,
    validate,
    validate_file,
)
from tradinghelper.schemas import PRICE_COLUMNS, Bar, PricesFile

CAL = NyseCalendar()
S = date(2026, 11, 24)
RECENT_START = CAL.shift(S, -(RECENT_SESSIONS - 1))

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CANONICAL_AAPL = FIXTURES / "prices" / "canonical_AAPL.json"
VALIDATE_FIXTURES = FIXTURES / "validate"


def _bars(start: date, end: date, *, closes: dict[date, float] | None = None) -> list[Bar]:
    """Barres valides sur les séances de `[start, end]` ; `closes` impose certains cours."""
    overrides = closes or {}
    bars: list[Bar] = []
    for day in CAL.sessions(start, end):
        close = overrides.get(day, 100.0)
        high, low = round(close * 1.01, 4), round(close * 0.99, 4)
        bars.append((day, close, high, low, close, close, 1000))
    return bars


def _write_prices(directory: Path, symbol: str, bars: list[Bar]) -> Path:
    prices = PricesFile(
        schema_version=1,
        symbol=symbol,
        currency="USD",
        source="yfinance",
        columns=PRICE_COLUMNS,
        last_updated=datetime(2026, 11, 24, 22, 0, tzinfo=UTC),
        bars=bars,
    )
    path = directory / f"{symbol}.json"
    path.write_text(dumps_prices(prices), encoding="utf-8")
    return path


def _write_json(directory: Path, symbol: str, data: Any) -> Path:
    path = directory / f"{symbol}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _canonical_data(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(CANONICAL_AAPL.read_text(encoding="utf-8"))
    data.update(changes)
    return data


def _validate(
    symbol: str, path: Path, *, in_universe: bool = True, all_history: bool = False
) -> FileResult:
    return validate_file(
        symbol,
        path,
        session=S,
        recent_start=RECENT_START,
        calendar=CAL,
        in_universe=in_universe,
        all_history=all_history,
    )


def _rules(result: FileResult) -> list[tuple[date | None, str]]:
    return [(v.date, v.rule) for v in result.violations]


# --- R1 : lecture, en-tête, symbole, filet de sécurité -----------------------------------------


def test_canonical_fixture_has_no_violation() -> None:
    result = _validate("AAPL", CANONICAL_AAPL)

    assert result.violations == []


def test_invalid_json_is_unreadable() -> None:
    result = _validate("invalid_json", VALIDATE_FIXTURES / "invalid_json.json")

    assert _rules(result) == [(None, "unreadable")]
    assert result.violations[0].symbol == "invalid_json"
    assert "JSON invalide" in result.violations[0].detail
    assert result.warnings == []


def test_missing_key_is_schema_violation(tmp_path: Path) -> None:
    data = _canonical_data()
    del data["currency"]

    result = _validate("AAPL", _write_json(tmp_path, "AAPL", data))

    assert _rules(result) == [(None, "schema")]
    assert "currency" in result.violations[0].detail


def test_schema_version_2_is_schema_violation(tmp_path: Path) -> None:
    result = _validate("AAPL", _write_json(tmp_path, "AAPL", _canonical_data(schema_version=2)))

    assert _rules(result) == [(None, "schema")]
    assert "schema_version" in result.violations[0].detail


def test_each_header_error_is_reported(tmp_path: Path) -> None:
    data = _canonical_data(currency="EUR", source="other")

    result = _validate("AAPL", _write_json(tmp_path, "AAPL", data))

    assert _rules(result) == [(None, "schema"), (None, "schema")]


@pytest.mark.parametrize(
    "data", [[1, 2, 3], "texte", {"schema_version": 1}], ids=["liste", "chaîne", "sans bars"]
)
def test_non_object_or_missing_bars_is_schema_violation(tmp_path: Path, data: Any) -> None:
    result = _validate("AAPL", _write_json(tmp_path, "AAPL", data))

    assert result.violations
    assert {v.rule for v in result.violations} == {"schema"}


def test_symbol_mismatch() -> None:
    result = _validate("MSFT", VALIDATE_FIXTURES / "symbol_mismatch" / "MSFT.json")

    assert _rules(result) == [(None, "symbol_mismatch")]
    assert "AAPL" in result.violations[0].detail


def test_row_violations_are_reported_with_header_ok(tmp_path: Path) -> None:
    data = _canonical_data()
    data["bars"][1] = ["2026-11-19", 228.1, 227.0, 227.8, 230.95, 229.7312, 51234000]

    result = _validate("AAPL", _write_json(tmp_path, "AAPL", data))

    assert _rules(result) == [
        (date(2026, 11, 19), "dates_not_increasing"),
        (date(2026, 11, 19), "ohlc_inconsistent"),
    ]


def test_safety_net_catches_what_rows_miss(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Si `check_rows` laisse passer une barre que `PricesFile` refuse, une violation `schema`
    est ajoutée : la validation reste équivalente au contrat (R1)."""
    data = _canonical_data()
    data["bars"][1] = ["2026-11-20", 228.1, 227.0, 227.8, 230.95, 229.7312, 51234000]

    def lenient_check_rows(*args: Any, **kwargs: Any) -> RowCheck:
        return RowCheck(bars=[], violations=[])

    monkeypatch.setattr(validate_mod, "check_rows", lenient_check_rows)

    result = _validate("AAPL", _write_json(tmp_path, "AAPL", data))

    assert _rules(result) == [(None, "schema")]
    assert "high" in result.violations[0].detail


# --- R3 : avertissements seulement sur un fichier sans violation -------------------------------


def test_no_warnings_when_violations(tmp_path: Path) -> None:
    bars = _bars(date(2026, 10, 1), date(2026, 11, 10))  # périmé
    path = _write_prices(tmp_path, "AAPL", bars)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["bars"].append(["2026-11-25", 100.0, 101.0, 99.0, 100.0, 100.0, 0])
    path.write_text(json.dumps(data), encoding="utf-8")

    result = _validate("AAPL", path)

    assert _rules(result) == [(date(2026, 11, 25), "after_last_session")]
    assert result.warnings == []


def test_stale_file_warned(tmp_path: Path) -> None:
    path = _write_prices(tmp_path, "AAPL", _bars(date(2026, 10, 1), date(2026, 11, 18)))

    result = _validate("AAPL", path)

    assert [(w.rule, w.value) for w in result.warnings] == [("stale", 4.0)]


def test_window_vs_all_history(tmp_path: Path) -> None:
    old_jump, recent_jump = date(2026, 10, 6), date(2026, 11, 20)
    closes = {old_jump: 160.0, recent_jump: 240.0}  # +60 %, puis +50 %
    closes |= {d: 160.0 for d in CAL.sessions(date(2026, 10, 7), date(2026, 11, 19))}
    closes |= {d: 240.0 for d in CAL.sessions(date(2026, 11, 23), S)}
    bars = _bars(date(2026, 10, 1), S, closes=closes)
    gap_old, gap_recent = date(2026, 10, 15), date(2026, 11, 17)
    bars = [b for b in bars if b[0] not in {gap_old, gap_recent}]
    path = _write_prices(tmp_path, "AAPL", bars)

    recent = _validate("AAPL", path)
    full = _validate("AAPL", path, all_history=True)

    assert [(w.rule, w.start) for w in recent.warnings] == [
        ("missing_session", gap_recent),
        ("large_move", recent_jump),
    ]
    assert [(w.rule, w.start) for w in full.warnings] == [
        ("missing_session", gap_old),
        ("missing_session", gap_recent),
        ("large_move", old_jump),
        ("large_move", recent_jump),
    ]


def test_zero_volume_in_window(tmp_path: Path) -> None:
    bars = _bars(date(2026, 11, 2), S)
    bars[-1] = (*bars[-1][:6], 0)
    path = _write_prices(tmp_path, "AAPL", bars)

    result = _validate("AAPL", path)

    assert [(w.rule, w.start) for w in result.warnings] == [("zero_volume", S)]


def test_orphan_gets_no_warning(tmp_path: Path) -> None:
    path = _write_prices(tmp_path, "OLD", _bars(date(2026, 10, 1), date(2026, 11, 2)))

    result = _validate("OLD", path, in_universe=False)

    assert result == FileResult(violations=[], warnings=[])


def test_fixture_dir_untouched(tmp_path: Path) -> None:
    copy = tmp_path / "AAPL.json"
    shutil.copy(CANONICAL_AAPL, copy)
    before = copy.read_bytes()

    _validate("AAPL", copy, all_history=True)

    assert copy.read_bytes() == before


# --- Validation d'un dossier (T10 : R3, R4, R5, R6) --------------------------------------------

NOW = datetime(2026, 11, 24, 22, 30, tzinfo=UTC)  # S = 2026-11-24


def _universe(*symbols: str, benchmark: str = "SPY") -> UniverseConfig:
    return UniverseConfig.model_validate(
        {
            "currency": "USD",
            "benchmark": benchmark,
            "tickers": [
                {"symbol": s, "name": s, "sector": "Test", "start": date(2026, 1, 2)}
                for s in symbols
            ],
        },
        context={"today": date(2026, 12, 31)},
    )


UNIVERSE = _universe("AAPL", "MSFT")


def _prices_dir(root: Path) -> Path:
    directory = root / "raw" / "prices"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _run_validate(
    root: Path,
    *,
    symbols: tuple[str, ...] | None = None,
    all_history: bool = False,
    universe: UniverseConfig = UNIVERSE,
) -> ValidateOutcome:
    return validate(
        universe,
        ValidateRequest(symbols=symbols, all_history=all_history),
        calendar=CAL,
        now=lambda: NOW,
        data_root=root,
    )


def _fresh(directory: Path, *symbols: str) -> None:
    for symbol in symbols:
        _write_prices(directory, symbol, _bars(date(2026, 10, 1), S))


def test_clean_directory(tmp_path: Path) -> None:
    _fresh(_prices_dir(tmp_path), "AAPL", "MSFT", "SPY")

    outcome = _run_validate(tmp_path)

    assert outcome.session == S
    assert outcome.run.files_checked == 3
    assert outcome.run.violations == []
    assert outcome.run.warnings == []
    assert outcome.run.exit_code == 0
    assert not outcome.has_violations
    assert outcome.run.args.symbols is None
    assert outcome.run.started_at == NOW


def test_missing_file_warning(tmp_path: Path) -> None:
    _fresh(_prices_dir(tmp_path), "AAPL")

    outcome = _run_validate(tmp_path)

    assert [(w.symbol, w.rule) for w in outcome.run.warnings] == [
        ("MSFT", "missing_file"),
        ("SPY", "missing_file"),
    ]
    assert outcome.run.exit_code == 0


def test_no_prices_dir_exit_0(tmp_path: Path) -> None:
    outcome = _run_validate(tmp_path / "absent")

    assert outcome.run.files_checked == 0
    assert outcome.run.exit_code == 0
    assert {w.rule for w in outcome.run.warnings} == {"missing_file"}


def test_orphan_stale_not_warned(tmp_path: Path) -> None:
    directory = _prices_dir(tmp_path)
    _fresh(directory, "AAPL", "MSFT", "SPY")
    _write_prices(directory, "OLD", _bars(date(2026, 9, 1), date(2026, 10, 1)))

    outcome = _run_validate(tmp_path)

    assert outcome.run.files_checked == 4
    assert outcome.run.warnings == []


def test_orphan_corrupted_is_violation(tmp_path: Path) -> None:
    directory = _prices_dir(tmp_path)
    _fresh(directory, "AAPL", "MSFT", "SPY")
    (directory / "readme.json").write_text("{tronqu", encoding="utf-8")

    outcome = _run_validate(tmp_path)

    assert [(v.symbol, v.rule) for v in outcome.run.violations] == [("readme", "unreadable")]
    assert outcome.run.exit_code == 1
    assert outcome.has_violations


def test_symbols_option_skips_orphans(tmp_path: Path) -> None:
    directory = _prices_dir(tmp_path)
    _fresh(directory, "AAPL")
    (directory / "readme.json").write_text("{tronqu", encoding="utf-8")

    outcome = _run_validate(tmp_path, symbols=("AAPL", "SPY"))

    assert outcome.run.files_checked == 1
    assert outcome.run.violations == []
    assert [(w.symbol, w.rule) for w in outcome.run.warnings] == [("SPY", "missing_file")]
    assert outcome.run.args.symbols == ["AAPL", "SPY"]


def test_late_ipo_no_missing_session(tmp_path: Path) -> None:
    """Fichier qui commence après le `start` de l'univers (introduction en bourse tardive)."""
    directory = _prices_dir(tmp_path)
    _fresh(directory, "MSFT", "SPY")
    _write_prices(directory, "AAPL", _bars(date(2026, 11, 19), S))

    outcome = _run_validate(tmp_path, all_history=True)

    assert outcome.run.warnings == []


def test_jump_outside_window_needs_all_history(tmp_path: Path) -> None:
    directory = _prices_dir(tmp_path)
    _fresh(directory, "MSFT", "SPY")
    jump = date(2026, 10, 6)
    closes = {d: 160.0 for d in CAL.sessions(jump, S)}
    _write_prices(directory, "AAPL", _bars(date(2026, 10, 1), S, closes=closes))

    assert _run_validate(tmp_path).run.warnings == []
    full = _run_validate(tmp_path, all_history=True).run.warnings
    assert [(w.rule, w.start, w.value) for w in full] == [("large_move", jump, 0.6)]


def test_results_sorted(tmp_path: Path) -> None:
    directory = _prices_dir(tmp_path)
    _fresh(directory, "AAPL")
    bars = _bars(date(2026, 11, 2), S)
    bars = [b for b in bars if b[0] != date(2026, 11, 17)]
    bars[-1] = (*bars[-1][:6], 0)
    _write_prices(directory, "MSFT", bars)
    for name, payload in (("ZZZ", "{"), ("BBB", "[]")):
        (directory / f"{name}.json").write_text(payload, encoding="utf-8")

    run = _run_validate(tmp_path).run

    assert [(v.symbol, v.rule) for v in run.violations] == [
        ("BBB", "schema"),
        ("ZZZ", "unreadable"),
    ]
    assert [(w.symbol, w.rule, w.start) for w in run.warnings] == [
        ("MSFT", "missing_session", date(2026, 11, 17)),
        ("MSFT", "zero_volume", S),
        ("SPY", "missing_file", None),
    ]


def test_exit_code_reflects_violations(tmp_path: Path) -> None:
    directory = _prices_dir(tmp_path)
    _fresh(directory, "AAPL", "SPY")
    _write_json(directory, "MSFT", _canonical_data(symbol="MSFT", schema_version=2))

    run = _run_validate(tmp_path).run

    assert run.exit_code == 1
    assert [(v.symbol, v.rule) for v in run.violations] == [("MSFT", "schema")]


def test_raw_files_untouched(tmp_path: Path) -> None:
    directory = _prices_dir(tmp_path)
    _fresh(directory, "AAPL", "SPY")
    _write_json(directory, "MSFT", _canonical_data(symbol="MSFT", schema_version=2))
    (directory / "readme.json").write_text("{tronqu", encoding="utf-8")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}

    _run_validate(tmp_path, all_history=True)

    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
    assert after == before
    assert not (tmp_path / "runs").exists()  # aucun rapport écrit par `validate()` (c'est la CLI)
