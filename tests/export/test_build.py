"""Tests de la construction pure des fichiers d'export (F08 — R6, R9 à R12, R14, R15)."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date

import numpy as np
import pytest
from pydantic import BaseModel

from tradinghelper.export.build import (
    MONEY_DECIMALS,
    PRICE_DECIMALS,
    RATIO_DECIMALS,
    RSI_DECIMALS,
    digest,
    render,
    rounded,
)
from tradinghelper.schemas import HealthRun, HealthValidate

# --- Rendu, empreinte, arrondi (T9) ------------------------------------------------------------


class _Sample(BaseModel):
    label: str
    value: float
    day: date
    items: list[int]


def test_decimal_grid_matches_spec() -> None:
    """Grille d'arrondi des Définitions de la spec (R14)."""
    assert (PRICE_DECIMALS, RSI_DECIMALS, RATIO_DECIMALS, MONEY_DECIMALS) == (4, 2, 4, 2)


def test_render_is_minified_utf8() -> None:
    sample = _Sample(label="Société générale", value=1.5, day=date(2026, 11, 23), items=[1, 2])

    content = render(sample)

    expected = '{"label":"Société générale","value":1.5,"day":"2026-11-23","items":[1,2]}'
    assert content == expected.encode("utf-8")


def test_render_refuses_nan() -> None:
    """Seconde barrière (R8, R14) : un NaN qui aurait échappé au modèle ne s'écrit jamais."""
    with pytest.raises(ValueError, match="JSON"):
        render(_Sample(label="x", value=math.nan, day=date(2026, 11, 23), items=[]))


def test_render_uses_json_aliases() -> None:
    run = HealthRun(
        session_date=date(2026, 11, 23),
        ingest=None,
        validate_=HealthValidate(exit_code=0, violations=0, warnings=2),
    )

    payload = json.loads(render(run))

    assert payload["validate"] == {"exit_code": 0, "violations": 0, "warnings": 2}
    assert "validate_" not in payload


def test_render_is_deterministic() -> None:
    sample = _Sample(label="a", value=0.1, day=date(2026, 1, 2), items=[3])

    assert render(sample) == render(sample)


def test_digest_is_16_hex_of_sha256() -> None:
    content = b'{"a":1}'

    assert digest(content) == hashlib.sha256(content).hexdigest()[:16]
    assert len(digest(b"")) == 16


def test_rounded_nan_to_none() -> None:
    assert rounded(np.array([np.nan, 1.23456, np.nan]), 4) == [None, 1.2346, None]


@pytest.mark.parametrize(
    ("decimals", "values", "expected"),
    [
        (4, [0.1 + 0.2, 228.10000001, 0.123449999, 0.0987654], [0.3, 228.1, 0.1234, 0.0988]),
        (2, [61.4249, 63.875, 100.0, 0.0], [61.42, 63.88, 100.0, 0.0]),
    ],
)
def test_rounded_decimals(decimals: int, values: list[float], expected: list[float]) -> None:
    result = rounded(np.array(values), decimals)

    assert result == pytest.approx(expected)
    for value in result:
        assert value is not None
        assert round(value, decimals) == value, value


def test_rounded_returns_python_floats() -> None:
    result = rounded(np.array([1.0, np.nan]), 4)

    assert type(result[0]) is float
    assert json.dumps(result) == "[1.0, null]"


def test_rounded_empty() -> None:
    assert rounded(np.array([], dtype=np.float64), 4) == []


def test_rounded_refuses_infinity() -> None:
    with pytest.raises(ValueError, match="infini"):
        rounded(np.array([1.0, np.inf]), 4)
