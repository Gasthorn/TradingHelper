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
    atomic_write_json,
    atomic_write_text,
    data_dir,
    dumps_prices,
    prices_path,
    read_prices,
    write_prices_if_changed,
)
from tradinghelper.schemas import PRICE_COLUMNS, Bar, PricesFile

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
