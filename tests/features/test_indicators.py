"""Tests des indicateurs techniques purs (F08 — R7, R8)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tradinghelper.features.indicators import bollinger, sma

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "export" / "indicators_reference.json"
TOL = 1e-4


@pytest.fixture(scope="module")
def reference() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def _close(reference: dict[str, Any]) -> np.ndarray[Any, np.dtype[np.float64]]:
    return np.asarray(reference["close"], dtype=np.float64)


def _assert_matches(actual: np.ndarray[Any, Any], expected: list[float | None]) -> None:
    assert actual.shape == (len(expected),)
    for index, (value, wanted) in enumerate(zip(actual.tolist(), expected, strict=True)):
        if wanted is None:
            assert math.isnan(value), f"index {index} : NaN attendu, obtenu {value}"
        else:
            assert value == pytest.approx(wanted, abs=TOL), f"index {index}"


@pytest.mark.parametrize("n", [5, 20])
def test_sma_reference_values(reference: dict[str, Any], n: int) -> None:
    _assert_matches(sma(_close(reference), n), reference[f"sma{n}"])


def test_bollinger_reference_values(reference: dict[str, Any]) -> None:
    middle, upper, lower = bollinger(_close(reference), n=20, k=2.0)

    _assert_matches(middle, reference["sma20"])
    _assert_matches(upper, reference["bb20_upper"])
    _assert_matches(lower, reference["bb20_lower"])


def test_bollinger_population_std() -> None:
    """Écart-type de population (ddof=0) : sur [1, 3], il vaut 1 (et non √2 avec ddof=1)."""
    _middle, upper, lower = bollinger(np.array([1.0, 3.0]), n=2, k=1.0)

    assert upper[1] == pytest.approx(3.0)
    assert lower[1] == pytest.approx(1.0)


@pytest.mark.parametrize("n", [1, 5, 20])
def test_sma_warmup_is_nan(n: int) -> None:
    result = sma(np.arange(1.0, 31.0), n)

    assert np.isnan(result[: n - 1]).all()
    assert not np.isnan(result[n - 1 :]).any()


def test_sma_window_one_is_identity() -> None:
    x = np.array([3.5, 1.25, 7.0])

    np.testing.assert_array_equal(sma(x, 1), x)


@pytest.mark.parametrize("length", [0, 1, 19])
def test_short_series_all_nan(length: int) -> None:
    x = np.linspace(10.0, 20.0, length)

    assert sma(x, 20).shape == (length,)
    assert np.isnan(sma(x, 20)).all()
    for band in bollinger(x, n=20):
        assert band.shape == (length,)
        assert np.isnan(band).all()


@pytest.mark.parametrize("n", [0, -1])
def test_invalid_window_raises(n: int) -> None:
    with pytest.raises(ValueError, match="fenêtre"):
        sma(np.arange(5.0), n)
    with pytest.raises(ValueError, match="fenêtre"):
        bollinger(np.arange(5.0), n=n)


def test_two_dimensional_input_raises() -> None:
    with pytest.raises(ValueError, match="1 dimension"):
        sma(np.ones((3, 3)), 2)


def test_input_not_modified() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0])
    before = x.copy()

    sma(x, 2)
    bollinger(x, n=2)

    np.testing.assert_array_equal(x, before)
