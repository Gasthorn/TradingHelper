"""Fixtures d'export du dashboard (spec F09 — R24) : à jour et conformes aux JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from dashboard_fixtures import FIXTURE_NAMES, FIXTURES_DIR, REGENERATE, build_fixture

REPO_ROOT = Path(__file__).resolve().parents[1]


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _schema_for(path: str) -> str:
    if path.startswith("tickers/"):
        return "export_ticker.schema.json"
    return f"export_{path.removesuffix('.json')}.schema.json"


def _load(name: str, path: str) -> Any:
    return json.loads((FIXTURES_DIR / name / path).read_bytes())


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixtures_up_to_date(name: str, tmp_path: Path) -> None:
    """La régénération produit exactement les fichiers commités, octet pour octet."""
    build_fixture(name, tmp_path / name)

    committed = _files(FIXTURES_DIR / name)
    assert committed, f"fixture {name} absente : {REGENERATE}"
    assert _files(tmp_path / name) == committed, f"fixture {name} périmée : {REGENERATE}"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixtures_match_json_schemas(name: str) -> None:
    for path, content in _files(FIXTURES_DIR / name).items():
        schema = json.loads((REPO_ROOT / "schemas" / _schema_for(path)).read_text("utf-8"))
        errors = list(Draft202012Validator(schema).iter_errors(json.loads(content)))
        assert errors == [], f"{name}/{path} : {errors[0].message}"


def test_m1_fixture_content() -> None:
    manifest = _load("m1", "manifest.json")
    assert [(t["symbol"], t["benchmark"]) for t in manifest["tickers"]] == [
        ("AAPL", False), ("BRK.B", False), ("NVDA", False), ("SPY", True),
    ]  # fmt: skip
    assert manifest["data_as_of"] == "2026-11-23"
    assert manifest["strategies"] == []

    aapl = _load("m1", "tickers/AAPL.json")
    assert {"2026-11-19", "2026-11-20", "2026-11-23"} <= set(aapl["series"]["date"])
    assert aapl["markers"] == []

    brk = _load("m1", "tickers/BRK.B.json")
    assert len(brk["series"]["date"]) < 200
    assert all(v is None for v in brk["series"]["sma200"])

    nvda = _load("m1", "tickers/NVDA.json")
    assert min(nvda["series"]["close"]) < 1

    overview = _load("m1", "overview.json")
    assert overview["leaderboard"] == overview["latest_signals"] == []
    assert overview["kpis"] == {"best_strategy_30d": None}


def test_empty_fixture_has_no_data() -> None:
    files = _files(FIXTURES_DIR / "empty")
    manifest = _load("empty", "manifest.json")

    assert manifest["data_as_of"] is None
    assert manifest["tickers"] == []
    assert not any(path.startswith("tickers/") for path in files)
    assert _load("empty", "overview.json")["tickers"] == []


def test_m1_signals_markers() -> None:
    markers = _load("m1-signals", "tickers/AAPL.json")["markers"]

    assert [(m["date"], m["action"], m["strategy_id"]) for m in markers] == [
        ("2026-11-20", "BUY", "lgbm_dir5_v3"),
        ("2026-11-23", "SELL", "lgbm_dir5_v3"),
    ]
    for symbol in ("BRK.B", "NVDA", "SPY"):
        assert _load("m1-signals", f"tickers/{symbol}.json")["markers"] == []
