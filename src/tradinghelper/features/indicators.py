"""Indicateurs techniques purs et vectorisés (F08 R7, R8 ; repris et étendus par F03 R1).

Conventions communes :
- entrée : série 1-D de prix (`float64`), du plus ancien au plus récent, jamais modifiée ;
- sortie : tableau de même longueur, `NaN` tant que la fenêtre est incomplète (warm-up) ;
- la valeur à l'index `t` ne dépend que des valeurs d'index `<= t` (fenêtres passées, P1).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
from numpy.lib.stride_tricks import sliding_window_view

FloatArray = npt.NDArray[np.float64]


def _as_series(x: npt.ArrayLike) -> FloatArray:
    series: FloatArray = np.asarray(x, dtype=np.float64)
    if series.ndim != 1:
        raise ValueError(f"série à 1 dimension attendue (reçu {series.ndim} dimensions)")
    return series


def _check_window(n: int) -> None:
    if n < 1:
        raise ValueError(f"taille de fenêtre invalide : {n} (doit être >= 1)")


def _windows(series: FloatArray, n: int) -> npt.NDArray[Any]:
    """Vue (sans copie) des fenêtres `series[t-n+1 .. t]` pour `t >= n-1`."""
    return sliding_window_view(series, n)


def sma(x: npt.ArrayLike, n: int) -> FloatArray:
    """Moyenne mobile simple sur `n` valeurs : `NaN` pour `t < n-1`.

    Moyenne de chaque fenêtre (et non somme cumulée) pour éviter toute dérive flottante.
    """
    _check_window(n)
    series = _as_series(x)
    out: FloatArray = np.full(series.shape, np.nan)
    if series.size >= n:
        out[n - 1 :] = _windows(series, n).mean(axis=1)
    return out


def bollinger(
    x: npt.ArrayLike, n: int = 20, k: float = 2.0
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Bandes de Bollinger `(milieu, haut, bas)` : milieu = `sma(x, n)`, bandes à `± k * std`,
    `std` = écart-type de **population** (`ddof=0`) sur la même fenêtre. `NaN` pour `t < n-1`."""
    _check_window(n)
    series = _as_series(x)
    middle = sma(series, n)
    std: FloatArray = np.full(series.shape, np.nan)
    if series.size >= n:
        std[n - 1 :] = _windows(series, n).std(axis=1, ddof=0)
    return middle, middle + k * std, middle - k * std
