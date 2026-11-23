"""Tests des contrats de données (F01 — R17, R8, R15 ; contrats §2 et §6)."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tradinghelper.schemas import (
    PRICE_COLUMNS,
    IngestTickerResult,
    IngestWarning,
    PricesFile,
    RunReport,
)

CONTRACTS = Path(__file__).resolve().parents[1] / "specs" / "03-data-contracts.md"


def _valid_prices() -> dict[str, Any]:
    """Fichier de prix valide, sous la forme JSON du contrat §2."""
    return {
        "schema_version": 1,
        "symbol": "AAPL",
        "currency": "USD",
        "source": "yfinance",
        "columns": list(PRICE_COLUMNS),
        "last_updated": "2026-11-23T22:41:05Z",
        "bars": [
            ["2026-11-20", 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000],
            ["2026-11-23", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000],
        ],
    }


def _with(**changes: Any) -> dict[str, Any]:
    data = _valid_prices()
    data.update(copy.deepcopy(changes))
    return data


def _without(key: str) -> dict[str, Any]:
    data = _valid_prices()
    del data[key]
    return data


def _with_bar(index: int, position: int, value: Any) -> dict[str, Any]:
    data = _valid_prices()
    data["bars"][index][position] = value
    return data


def test_price_columns_match_contract() -> None:
    assert PRICE_COLUMNS == ("date", "open", "high", "low", "close", "adj_close", "volume")


def test_prices_model_accepts_valid_file() -> None:
    prices = PricesFile.model_validate(_valid_prices())

    assert prices.symbol == "AAPL"
    assert len(prices.bars) == 2
    assert prices.bars[0][0].isoformat() == "2026-11-20"
    assert prices.bars[1][6] == 48765000
    assert prices.last_updated.utcoffset() is not None
    assert prices.last_updated.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_prices_model_accepts_empty_bars() -> None:
    assert PricesFile.model_validate(_with(bars=[])).bars == []


INVALID_CASES: dict[str, tuple[dict[str, Any], str]] = {
    "dates non croissantes": (
        _with(
            bars=[
                ["2026-11-23", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000],
                ["2026-11-20", 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000],
            ]
        ),
        "2026-11-20",
    ),
    "date dupliquée": (
        _with(
            bars=[
                ["2026-11-20", 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000],
                ["2026-11-20", 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000],
            ]
        ),
        "2026-11-20",
    ),
    "prix nul": (_with_bar(0, 1, 0.0), "bars"),
    "prix négatif": (_with_bar(0, 5, -1.0), "bars"),
    "prix NaN": (_with_bar(0, 4, float("nan")), "bars"),
    "prix non arrondi à 4 décimales": (_with_bar(0, 4, 230.95001), "2026-11-20"),
    "low > open": (_with_bar(0, 3, 228.2), "2026-11-20"),
    "low > close": (_with_bar(1, 3, 232.5), "2026-11-23"),
    "high < open": (_with_bar(1, 2, 230.0), "2026-11-23"),
    "high < close": (_with_bar(0, 2, 230.0), "2026-11-20"),
    "volume négatif": (_with_bar(0, 6, -1), "bars"),
    "volume non entier": (_with_bar(0, 6, 1.5), "bars"),
    "barre trop courte": (_with(bars=[["2026-11-20", 228.1, 231.45]]), "bars"),
    "date invalide": (_with_bar(0, 0, "2026-02-30"), "bars"),
    "columns différentes": (_with(columns=["date", "close"]), "columns"),
    "columns dans le désordre": (
        _with(columns=["date", "open", "high", "low", "adj_close", "close", "volume"]),
        "columns",
    ),
    "currency EUR": (_with(currency="EUR"), "currency"),
    "source inconnue": (_with(source="stooq"), "source"),
    "schema_version 2": (_with(schema_version=2), "schema_version"),
    "symbole invalide": (_with(symbol="aapl"), "symbol"),
    "last_updated sans fuseau": (_with(last_updated="2026-11-23T22:41:05"), "last_updated"),
    "last_updated hors UTC": (_with(last_updated="2026-11-23T22:41:05+01:00"), "last_updated"),
    "clé inconnue": (_with(extra_field=1), "extra_field"),
    "schema_version absent": (_without("schema_version"), "schema_version"),
    "columns absent": (_without("columns"), "columns"),
    "last_updated absent": (_without("last_updated"), "last_updated"),
}


@pytest.mark.parametrize(
    ("data", "expected"),
    list(INVALID_CASES.values()),
    ids=list(INVALID_CASES),
)
def test_prices_model_rejects_rule_violations(data: dict[str, Any], expected: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        PricesFile.model_validate(data)

    assert expected in str(excinfo.value)


def test_prices_model_is_immutable() -> None:
    prices = PricesFile.model_validate(_valid_prices())

    with pytest.raises(ValidationError):
        prices.symbol = "MSFT"  # type: ignore[misc]


# --- Exemples du contrat (le document et les modèles ne doivent pas diverger) -------------------


def _contract_example(section: str) -> Any:
    """Premier bloc ```json de la section `## {section}.` de `03-data-contracts.md`."""
    text = CONTRACTS.read_text(encoding="utf-8")
    start = text.index(f"\n## {section}.")
    end = text.find("\n## ", start + 1)
    block = re.search(r"```json\n(.*?)\n```", text[start : end if end != -1 else None], re.S)
    assert block is not None, f"pas de bloc JSON dans la section {section}"
    return json.loads(block.group(1))


def test_contract_example_prices_is_valid() -> None:
    PricesFile.model_validate(_contract_example("2"))


def test_contract_example_run_report_is_valid() -> None:
    report = RunReport.model_validate(_contract_example("6"))

    assert report.session_date.isoformat() == "2026-11-23"
    assert [t.status for t in report.ingest[0].tickers] == ["ok", "failed"]


# --- Rapport de run (contrat §6) ----------------------------------------------------------------


def _ticker(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "symbol": "AAPL",
        "status": "ok",
        "mode": "incremental",
        "bars_added": 1,
        "bars_revised": 0,
        "history_rewritten": False,
        "rewrite_reason": None,
        "attempts": 1,
        "error": None,
    }
    data.update(changes)
    return data


def _report(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": 1,
        "session_date": "2026-11-23",
        "ingest": [
            {
                "started_at": "2026-11-23T22:31:02Z",
                "finished_at": "2026-11-23T22:32:10Z",
                "duration_s": 68.0,
                "args": {"symbols": None, "full": False, "start": None},
                "exit_code": 0,
                "tickers": [_ticker()],
                "warnings": [{"symbol": "NVDA", "date": "2026-11-22", "rule": "non_session_date"}],
            }
        ],
    }
    data.update(changes)
    return data


def test_run_report_roundtrip() -> None:
    report = RunReport.model_validate(_report())
    dumped = report.model_dump(mode="json")

    assert RunReport.model_validate(dumped) == report
    assert dumped["ingest"][0]["started_at"] == "2026-11-23T22:31:02Z"
    assert dumped["session_date"] == "2026-11-23"


def test_run_report_without_ingest_section() -> None:
    report = RunReport.model_validate({"schema_version": 1, "session_date": "2026-11-23"})

    assert report.ingest == []


def test_run_report_preserves_unknown_sections() -> None:
    validate_section = {"errors": [], "warnings": [{"symbol": "AAPL", "rule": "stale"}]}
    report = RunReport.model_validate(_report(validate=validate_section))

    assert report.model_dump(mode="json")["validate"] == validate_section


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "skipped"),
        ("mode", "partial"),
        ("rewrite_reason", "manual"),
        ("bars_added", -1),
        ("attempts", -1),
        ("symbol", "aapl"),
    ],
)
def test_ingest_ticker_result_enums(field: str, value: Any) -> None:
    with pytest.raises(ValidationError) as excinfo:
        IngestTickerResult.model_validate(_ticker(**{field: value}))

    assert field in str(excinfo.value)


def test_warning_rule_enum() -> None:
    with pytest.raises(ValidationError):
        IngestWarning.model_validate({"symbol": "AAPL", "date": None, "rule": "unknown_rule"})


def test_unchanged_ticker_has_no_mode() -> None:
    result = IngestTickerResult.model_validate(_ticker(status="unchanged", mode=None, bars_added=0))

    assert result.mode is None


INCONSISTENT_TICKERS: dict[str, dict[str, Any]] = {
    "réécrit sans raison": _ticker(history_rewritten=True, rewrite_reason=None),
    "raison sans réécriture": _ticker(history_rewritten=False, rewrite_reason="revision"),
    "échec sans erreur": _ticker(status="failed", error=None),
    "succès avec erreur": _ticker(status="ok", error="boom"),
}


@pytest.mark.parametrize(
    "data", list(INCONSISTENT_TICKERS.values()), ids=list(INCONSISTENT_TICKERS)
)
def test_ingest_ticker_result_consistency(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        IngestTickerResult.model_validate(data)


def _run_with(**changes: Any) -> dict[str, Any]:
    data = _report()
    data["ingest"][0].update(changes)
    return data


INVALID_RUNS: dict[str, dict[str, Any]] = {
    "fin avant début": _run_with(finished_at="2026-11-23T22:30:00Z"),
    "horodatage hors UTC": _run_with(started_at="2026-11-23T23:31:02+01:00"),
    "code de sortie 2": _run_with(exit_code=2),
    "durée négative": _run_with(duration_s=-1.0),
    "clé inconnue dans une exécution": _run_with(extra=1),
}


@pytest.mark.parametrize("data", list(INVALID_RUNS.values()), ids=list(INVALID_RUNS))
def test_ingest_run_rejects_invalid(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RunReport.model_validate(data)


def test_run_report_requires_schema_version_and_session_date() -> None:
    with pytest.raises(ValidationError) as excinfo:
        RunReport.model_validate({"ingest": []})

    assert "schema_version" in str(excinfo.value)
    assert "session_date" in str(excinfo.value)
