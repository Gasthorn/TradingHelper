"""Contrats de données (source de vérité de `specs/03-data-contracts.md`).

`th schemas` génère les JSON Schemas de `schemas/` depuis ces modèles. Toute modification
de contrat incrémente `schema_version`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    field_validator,
)

from tradinghelper.config import Symbol

PRICE_DECIMALS: Final = 4

PRICE_COLUMNS: Final = ("date", "open", "high", "low", "close", "adj_close", "volume")

# Prix strictement positif et fini (NaN et infinis refusés).
Price = Annotated[float, Field(gt=0, allow_inf_nan=False)]

# Une barre = une ligne de `bars`, dans l'ordre de `PRICE_COLUMNS`.
Bar = tuple[date, Price, Price, Price, Price, Price, NonNegativeInt]

PriceColumns = tuple[
    Literal["date"],
    Literal["open"],
    Literal["high"],
    Literal["low"],
    Literal["close"],
    Literal["adj_close"],
    Literal["volume"],
]


class _Contract(BaseModel):
    """Base des contrats : clés inconnues refusées, objets immuables."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PricesFile(_Contract):
    """Prix bruts d'un symbole — `data/raw/prices/{SYMBOL}.json` (contrat §2)."""

    # Pas de valeur par défaut : chaque clé du contrat est obligatoire dans le fichier
    # (et marquée `required` dans le JSON Schema généré).
    schema_version: Literal[1]
    symbol: Symbol
    currency: Literal["USD"]
    source: Literal["yfinance"]
    columns: PriceColumns
    last_updated: AwareDatetime
    bars: list[Bar]

    @field_validator("last_updated")
    @classmethod
    def _utc(cls, value: AwareDatetime) -> AwareDatetime:
        offset = value.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("last_updated doit être en UTC")
        return value

    @field_validator("bars")
    @classmethod
    def _bar_rules(cls, bars: list[Bar]) -> list[Bar]:
        previous: date | None = None
        for day, open_, high, low, close, adj_close, _volume in bars:
            where = day.isoformat()
            if previous is not None and day <= previous:
                raise ValueError(
                    f"{where} : dates non strictement croissantes (après {previous.isoformat()})"
                )
            previous = day
            for price in (open_, high, low, close, adj_close):
                if round(price, PRICE_DECIMALS) != price:
                    raise ValueError(f"{where} : prix {price!r} non arrondi à 4 décimales")
            if low > min(open_, close):
                raise ValueError(f"{where} : low {low} > min(open, close)")
            if high < max(open_, close):
                raise ValueError(f"{where} : high {high} < max(open, close)")
        return bars
