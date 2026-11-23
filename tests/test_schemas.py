"""Tests des contrats de données (F01 — R17, R8 ; contrat §2)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from tradinghelper.schemas import PRICE_COLUMNS, PricesFile


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
