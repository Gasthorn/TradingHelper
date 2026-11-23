"""Tests du stockage des données (F01 — R8 ; contrat §2, sérialisation canonique)."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tradinghelper.data import storage
from tradinghelper.data.storage import atomic_write_json, atomic_write_text, dumps_prices
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
