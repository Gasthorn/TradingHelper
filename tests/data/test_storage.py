"""Tests du stockage des données (F01 — R8 ; contrat §2, sérialisation canonique)."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tradinghelper.data import storage
from tradinghelper.data.storage import (
    PricesFileError,
    RunReportError,
    append_run_report_entry,
    atomic_write_json,
    atomic_write_text,
    data_dir,
    dumps_prices,
    prices_path,
    read_prices,
    run_report_path,
    update_run_report,
    write_prices_if_changed,
)
from tradinghelper.schemas import (
    PRICE_COLUMNS,
    Bar,
    IngestArgs,
    IngestRun,
    IngestTickerResult,
    PricesFile,
    RunReport,
    ValidateRun,
    ValidateViolation,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "prices"
CANONICAL_AAPL = FIXTURES / "canonical_AAPL.json"


def _prices(bars: list[Bar], last_updated: datetime | None = None) -> PricesFile:
    return PricesFile(
        schema_version=1,
        symbol="AAPL",
        currency="USD",
        source="yfinance",
        columns=PRICE_COLUMNS,
        last_updated=last_updated or datetime(2026, 11, 23, 22, 41, 5, tzinfo=UTC),
        bars=bars,
    )


# --- Sérialisation canonique -------------------------------------------------------------------


def test_dumps_prices_matches_canonical_fixture() -> None:
    expected = CANONICAL_AAPL.read_bytes().decode("utf-8")
    prices = PricesFile.model_validate_json(expected)

    assert dumps_prices(prices) == expected


def test_canonical_fixture_has_one_bar_per_line() -> None:
    text = dumps_prices(PricesFile.model_validate_json(CANONICAL_AAPL.read_text(encoding="utf-8")))
    bar_lines = [line for line in text.splitlines() if line.startswith('    ["')]

    assert len(bar_lines) == 3
    assert "\r" not in text
    assert text.endswith("}\n")


@pytest.mark.parametrize(
    ("value", "expected"),
    [(228.1, "228.1"), (231.0, "231.0"), (229.7312, "229.7312"), (0.0001, "0.0001")],
)
def test_dumps_float_shortest_repr(value: float, expected: str) -> None:
    bar: Bar = (date(2026, 11, 20), value, value, value, value, value, 1)

    lines = dumps_prices(_prices([bar])).splitlines()
    line = next(line for line in lines if '"2026-11-20"' in line)

    assert line.strip().rstrip(",") == f'["2026-11-20", {", ".join([expected] * 5)}, 1]'


def test_dumps_empty_bars() -> None:
    text = dumps_prices(_prices([]))

    assert '  "bars": []\n}\n' in text
    assert PricesFile.model_validate_json(text).bars == []


def test_dumps_last_updated_is_utc_seconds_with_z() -> None:
    stamp = datetime(2026, 11, 23, 22, 41, 5, 987654, tzinfo=UTC)

    text = dumps_prices(_prices([], last_updated=stamp))

    assert '"last_updated": "2026-11-23T22:41:05Z"' in text


def test_roundtrip_is_byte_identical() -> None:
    first = dumps_prices(PricesFile.model_validate_json(CANONICAL_AAPL.read_text(encoding="utf-8")))
    second = dumps_prices(PricesFile.model_validate_json(first))

    assert first == second


def test_dumps_output_is_valid_json_matching_model() -> None:
    prices = PricesFile.model_validate_json(CANONICAL_AAPL.read_text(encoding="utf-8"))

    reparsed = PricesFile.model_validate(json.loads(dumps_prices(prices)))

    assert reparsed == prices


# --- Écriture atomique -------------------------------------------------------------------------


def test_atomic_write_text_writes_exact_bytes_lf(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "file.json"

    atomic_write_text(target, "a\nb\n")

    assert target.read_bytes() == b"a\nb\n"


def test_atomic_write_text_replaces_existing(tmp_path: Path) -> None:
    target = tmp_path / "file.json"
    target.write_bytes(b"old")

    atomic_write_text(target, "new\n")

    assert target.read_bytes() == b"new\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["file.json"]


def test_atomic_write_failure_keeps_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "file.json"
    target.write_bytes(b"original")

    def failing_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("disque plein (simulé)")

    monkeypatch.setattr(storage.os, "replace", failing_replace)

    with pytest.raises(OSError, match="simulé"):
        atomic_write_text(target, "nouveau contenu\n")

    assert target.read_bytes() == b"original"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["file.json"]


def test_atomic_write_json_format(tmp_path: Path) -> None:
    target = tmp_path / "report.json"

    atomic_write_json(target, {"b": [1, 2], "a": "éè"})

    expected = '{\n  "b": [\n    1,\n    2\n  ],\n  "a": "éè"\n}\n'
    assert target.read_bytes().decode("utf-8") == expected


# --- Lecture validée (R9) ----------------------------------------------------------------------

BARS: list[Bar] = [
    (date(2026, 11, 20), 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000),
    (date(2026, 11, 23), 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000),
]
NOW = datetime(2026, 11, 24, 22, 31, 2, tzinfo=UTC)
LATER = datetime(2026, 11, 25, 22, 31, 2, tzinfo=UTC)


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_prices(tmp_path / "AAPL.json") is None


def test_read_valid_file(tmp_path: Path) -> None:
    target = tmp_path / "AAPL.json"
    target.write_bytes(CANONICAL_AAPL.read_bytes())

    prices = read_prices(target)

    assert prices is not None
    assert prices.symbol == "AAPL"
    assert len(prices.bars) == 3


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b'{"schema_version": 1, "bars": [', "JSON invalide"),
        (b"", "JSON invalide"),
        (b"\xff\xfe\x00", "JSON invalide"),
    ],
    ids=["tronqué", "vide", "non UTF-8"],
)
def test_read_invalid_json_raises(tmp_path: Path, content: bytes, reason: str) -> None:
    target = tmp_path / "AAPL.json"
    target.write_bytes(content)

    with pytest.raises(PricesFileError) as excinfo:
        read_prices(target)

    assert reason in str(excinfo.value)
    assert excinfo.value.path == target
    assert target.as_posix() in str(excinfo.value)


def test_read_schema_violation_raises(tmp_path: Path) -> None:
    data = json.loads(CANONICAL_AAPL.read_text(encoding="utf-8"))
    data["bars"][1][2] = 1.0  # high < low
    target = tmp_path / "AAPL.json"
    target.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PricesFileError) as excinfo:
        read_prices(target)

    assert "non conforme au contrat" in str(excinfo.value)
    assert "2026-11-20" in str(excinfo.value)


# --- Écriture conditionnelle (R8, R2) ----------------------------------------------------------


def test_write_if_changed_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "raw" / "prices" / "AAPL.json"

    assert write_prices_if_changed(target, "AAPL", BARS, NOW) is True

    written = read_prices(target)
    assert written is not None
    assert written.bars == BARS
    assert written.last_updated == NOW
    assert target.read_bytes().decode("utf-8") == dumps_prices(written)


def test_write_if_changed_skips_identical_bars(tmp_path: Path) -> None:
    target = tmp_path / "AAPL.json"
    write_prices_if_changed(target, "AAPL", BARS, NOW)
    before = target.read_bytes()
    mtime = target.stat().st_mtime_ns

    assert write_prices_if_changed(target, "AAPL", list(BARS), LATER) is False

    assert target.read_bytes() == before
    assert target.stat().st_mtime_ns == mtime


def test_write_if_changed_updates_last_updated_when_bars_change(tmp_path: Path) -> None:
    target = tmp_path / "AAPL.json"
    write_prices_if_changed(target, "AAPL", BARS[:1], NOW)

    assert write_prices_if_changed(target, "AAPL", BARS, LATER) is True

    written = read_prices(target)
    assert written is not None
    assert written.bars == BARS
    assert written.last_updated == LATER


def test_write_if_changed_overwrites_corrupted_file(tmp_path: Path) -> None:
    """La décision de ne pas écraser un fichier corrompu (R9) appartient à l'ingestion ;
    une écriture explicite (ex. backfill `--full`) remplace le fichier."""
    target = tmp_path / "AAPL.json"
    target.write_bytes(b"{corrompu")

    assert write_prices_if_changed(target, "AAPL", BARS, NOW) is True
    assert read_prices(target) is not None


def test_write_if_changed_rejects_invalid_bars(tmp_path: Path) -> None:
    target = tmp_path / "AAPL.json"
    bad: list[Bar] = [(date(2026, 11, 20), 228.1, 1.0, 227.8, 230.95, 229.7312, 1)]

    with pytest.raises(ValueError, match="high"):
        write_prices_if_changed(target, "AAPL", bad, NOW)

    assert not target.exists()


# --- Emplacements ------------------------------------------------------------------------------


def test_data_dir_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TH_DATA_DIR", str(tmp_path))

    assert data_dir() == tmp_path


def test_data_dir_default_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TH_DATA_DIR", raising=False)
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(repo_root / "tests")

    assert data_dir() == repo_root / "data"


def test_data_dir_blank_env_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TH_DATA_DIR", "  ")
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(repo_root)

    assert data_dir() == repo_root / "data"


def test_prices_path_keeps_config_symbol(tmp_path: Path) -> None:
    assert prices_path(tmp_path, "BRK.B") == tmp_path / "raw" / "prices" / "BRK.B.json"


def test_run_report_path_named_after_session(tmp_path: Path) -> None:
    assert run_report_path(tmp_path, date(2026, 11, 23)) == tmp_path / "runs" / "2026-11-23.json"


# --- Rapport de run (R15) ----------------------------------------------------------------------

SESSION = date(2026, 11, 23)


def _run(started_minute: int = 31, symbol: str = "AAPL") -> IngestRun:
    return IngestRun(
        started_at=datetime(2026, 11, 23, 22, started_minute, 2, tzinfo=UTC),
        finished_at=datetime(2026, 11, 23, 22, started_minute, 50, tzinfo=UTC),
        duration_s=48.0,
        args=IngestArgs(symbols=None, full=False, start=None),
        exit_code=0,
        tickers=[
            IngestTickerResult(
                symbol=symbol,
                status="ok",
                mode="incremental",
                bars_added=1,
                bars_revised=0,
                history_rewritten=False,
                rewrite_reason=None,
                attempts=1,
                error=None,
            )
        ],
        warnings=[],
    )


def _load_report(path: Path) -> RunReport:
    return RunReport.model_validate_json(path.read_text(encoding="utf-8"))


def test_update_report_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "runs" / "2026-11-23.json"

    update_run_report(target, SESSION, _run())

    report = _load_report(target)
    assert report.schema_version == 1
    assert report.session_date == SESSION
    assert report.ingest == [_run()]
    text = target.read_bytes().decode("utf-8")
    assert text.endswith("}\n")
    assert "\r" not in text


def test_update_report_appends_ingest_run(tmp_path: Path) -> None:
    target = tmp_path / "2026-11-23.json"
    update_run_report(target, SESSION, _run(31, "AAPL"))

    update_run_report(target, SESSION, _run(45, "MSFT"))

    assert [run.tickers[0].symbol for run in _load_report(target).ingest] == ["AAPL", "MSFT"]


def test_update_report_preserves_other_sections(tmp_path: Path) -> None:
    target = tmp_path / "2026-11-23.json"
    signal_section = {"errors": [], "warnings": [{"symbol": "AAPL", "rule": "stale"}]}
    target.write_text(
        json.dumps({"schema_version": 1, "session_date": "2026-11-23", "signal": signal_section}),
        encoding="utf-8",
    )

    update_run_report(target, SESSION, _run())

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["signal"] == signal_section
    assert len(data["ingest"]) == 1


def test_update_report_preserves_typed_validate_section(tmp_path: Path) -> None:
    """La section `validate` (F02) est réécrite sous sa clé JSON, jamais sous `validate_`."""
    target = tmp_path / "2026-11-23.json"
    validate_run = {
        "started_at": "2026-11-23T22:33:00Z",
        "finished_at": "2026-11-23T22:33:01Z",
        "duration_s": 1.0,
        "args": {"symbols": None, "all_history": False},
        "exit_code": 0,
        "files_checked": 2,
        "violations": [],
        "warnings": [],
    }
    target.write_text(
        json.dumps({"schema_version": 1, "session_date": "2026-11-23", "validate": [validate_run]}),
        encoding="utf-8",
    )

    update_run_report(target, SESSION, _run())

    data = json.loads(target.read_text(encoding="utf-8"))
    assert "validate_" not in data
    assert data["validate"] == [validate_run]
    assert len(data["ingest"]) == 1


def test_update_report_does_not_add_empty_validate_section(tmp_path: Path) -> None:
    target = tmp_path / "2026-11-23.json"
    update_run_report(target, SESSION, _run(31))

    update_run_report(target, SESSION, _run(45))

    assert "validate" not in json.loads(target.read_text(encoding="utf-8"))


def test_update_report_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "2026-11-23.json"
    update_run_report(target, SESSION, _run())
    before = target.read_bytes()

    def failing_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("coupure (simulée)")

    monkeypatch.setattr(storage.os, "replace", failing_replace)

    with pytest.raises(OSError, match="simulée"):
        update_run_report(target, SESSION, _run(45))

    assert target.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-11-23.json"]


def test_update_report_rejects_other_session(tmp_path: Path) -> None:
    target = tmp_path / "2026-11-23.json"
    update_run_report(target, SESSION, _run())
    before = target.read_bytes()

    with pytest.raises(RunReportError, match="2026-11-24"):
        update_run_report(target, date(2026, 11, 24), _run())

    assert target.read_bytes() == before


@pytest.mark.parametrize(
    "content",
    [b"{tronqu", b'{"schema_version": 2, "session_date": "2026-11-23"}'],
    ids=["JSON invalide", "non conforme"],
)
def test_update_report_refuses_corrupted_report(tmp_path: Path, content: bytes) -> None:
    target = tmp_path / "2026-11-23.json"
    target.write_bytes(content)

    with pytest.raises(RunReportError) as excinfo:
        update_run_report(target, SESSION, _run())

    assert target.as_posix() in str(excinfo.value)
    assert target.read_bytes() == content


# --- Ajout générique d'une entrée au rapport (F02 — R7) -----------------------------------------


def _validate_run(exit_code: int = 0) -> ValidateRun:
    violations = (
        [ValidateViolation(symbol="AAPL", date=SESSION, rule="ohlc_inconsistent", detail="x")]
        if exit_code
        else []
    )
    return ValidateRun.model_validate(
        {
            "started_at": "2026-11-23T22:33:00Z",
            "finished_at": "2026-11-23T22:33:01Z",
            "duration_s": 1.0,
            "args": {"symbols": None, "all_history": False},
            "exit_code": exit_code,
            "files_checked": 2,
            "violations": [v.model_dump(mode="json") for v in violations],
            "warnings": [],
        }
    )


def test_append_entry_creates_report_with_validate_only(tmp_path: Path) -> None:
    target = tmp_path / "runs" / "2026-11-23.json"

    append_run_report_entry(target, SESSION, "validate", _validate_run(1))

    data = json.loads(target.read_text(encoding="utf-8"))
    assert list(data) == ["schema_version", "session_date", "validate"]
    assert data["validate"][0]["exit_code"] == 1
    assert _load_report(target).validate_ == [_validate_run(1)]


def test_append_validate_keeps_ingest_section(tmp_path: Path) -> None:
    target = tmp_path / "2026-11-23.json"
    update_run_report(target, SESSION, _run())
    ingest_before = json.loads(target.read_text(encoding="utf-8"))["ingest"]

    append_run_report_entry(target, SESSION, "validate", _validate_run())
    append_run_report_entry(target, SESSION, "validate", _validate_run(1))

    data = json.loads(target.read_text(encoding="utf-8"))
    assert list(data) == ["schema_version", "session_date", "ingest", "validate"]
    assert data["ingest"] == ingest_before
    assert [run["exit_code"] for run in data["validate"]] == [0, 1]


def test_append_ingest_keeps_validate_section(tmp_path: Path) -> None:
    target = tmp_path / "2026-11-23.json"
    append_run_report_entry(target, SESSION, "validate", _validate_run())
    validate_before = json.loads(target.read_text(encoding="utf-8"))["validate"]

    append_run_report_entry(target, SESSION, "ingest", _run())

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["validate"] == validate_before
    assert len(data["ingest"]) == 1
    assert "validate_" not in data


def test_ingest_only_report_bytes_unchanged_after_ingest_append(tmp_path: Path) -> None:
    target = tmp_path / "2026-11-23.json"
    update_run_report(target, SESSION, _run(31, "AAPL"))
    before = json.loads(target.read_text(encoding="utf-8"))

    append_run_report_entry(target, SESSION, "ingest", _run(45, "MSFT"))

    after = json.loads(target.read_text(encoding="utf-8"))
    expected = {**before, "ingest": [*before["ingest"], _run(45, "MSFT").model_dump(mode="json")]}
    assert after == expected
    assert target.read_text(encoding="utf-8") == json.dumps(expected, indent=2) + "\n"


def test_append_entry_refuses_other_session(tmp_path: Path) -> None:
    target = tmp_path / "2026-11-23.json"
    append_run_report_entry(target, SESSION, "validate", _validate_run())
    before = target.read_bytes()

    with pytest.raises(RunReportError, match="2026-11-24"):
        append_run_report_entry(target, date(2026, 11, 24), "validate", _validate_run())

    assert target.read_bytes() == before


@pytest.mark.parametrize(
    "content",
    [b"{tronqu", b'{"schema_version": 1, "session_date": "2026-11-23", "validate": [{}]}'],
    ids=["JSON invalide", "section validate non conforme"],
)
def test_append_entry_refuses_unreadable_report(tmp_path: Path, content: bytes) -> None:
    target = tmp_path / "2026-11-23.json"
    target.write_bytes(content)

    with pytest.raises(RunReportError):
        append_run_report_entry(target, SESSION, "validate", _validate_run())

    assert target.read_bytes() == content


def test_append_entry_rejects_mismatched_section(tmp_path: Path) -> None:
    target = tmp_path / "2026-11-23.json"

    with pytest.raises(TypeError):
        append_run_report_entry(target, SESSION, "ingest", _validate_run())

    assert not target.exists()


# --- Liste des fichiers de prix et lecture JSON brute (F02 — R1, R5) ----------------------------


def test_price_files_lists_json_sorted(tmp_path: Path) -> None:
    for name in ("SPY.json", "AAPL.json", "BRK.B.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")

    files = storage.price_files(tmp_path)

    assert list(files) == ["AAPL", "BRK.B", "SPY"]
    assert files["BRK.B"] == tmp_path / "BRK.B.json"


def test_price_files_ignores_tmp_hidden_and_non_json(tmp_path: Path) -> None:
    (tmp_path / "AAPL.json").write_text("{}", encoding="utf-8")
    for name in (".AAPL.json.abc123.tmp", ".hidden.json", "notes.txt", "AAPL.json.bak"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / "sub.json").mkdir()

    assert list(storage.price_files(tmp_path)) == ["AAPL"]


def test_price_files_missing_dir_is_empty(tmp_path: Path) -> None:
    assert storage.price_files(tmp_path / "absent") == {}


@pytest.mark.parametrize(
    "content",
    [b"{tronqu", b'{"a": "\xff"}', b""],
    ids=["JSON invalide", "UTF-8 invalide", "vide"],
)
def test_read_json_invalid_raises(tmp_path: Path, content: bytes) -> None:
    target = tmp_path / "AAPL.json"
    target.write_bytes(content)

    with pytest.raises(PricesFileError) as excinfo:
        storage.read_json(target)

    assert excinfo.value.path == target


def test_read_json_returns_value(tmp_path: Path) -> None:
    target = tmp_path / "AAPL.json"
    target.write_text('{"symbol": "AAPL", "bars": [["2026-11-23", 1.5, 2]]}', encoding="utf-8")

    assert storage.read_json(target) == {"symbol": "AAPL", "bars": [["2026-11-23", 1.5, 2]]}


def test_read_json_keeps_nan_literal(tmp_path: Path) -> None:
    """`NaN` est lu tel quel : c'est la règle `non_positive_price` qui le refuse (F02 R2)."""
    target = tmp_path / "AAPL.json"
    target.write_text('{"bars": [[NaN]]}', encoding="utf-8")

    value = storage.read_json(target)

    assert isinstance(value, dict)
    bars = value["bars"]
    assert isinstance(bars, list)
    assert isinstance(bars[0], list)
    assert bars[0][0] != bars[0][0]  # NaN
