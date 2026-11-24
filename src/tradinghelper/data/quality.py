"""Règles de qualité des données (F02 R2, R3) : fonctions pures, sans E/S ni horloge.

Le calendrier NYSE y entre sous forme de fonctions (`is_session`) ou de listes de séances, pour
garder ces règles testables isolément (CLAUDE.md : fonctions pures isolées des effets de bord).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date

from pydantic import JsonValue

from tradinghelper.schemas import Bar, BlockingRule, ValidateViolation

ROW_LENGTH = 7  # date, open, high, low, close, adj_close, volume (contrat §2)


@dataclass(frozen=True)
class RowCheck:
    """Résultat de `check_rows` : barres typées (vides dès qu'une violation existe) et
    violations bloquantes, dans l'ordre des lignes."""

    bars: list[Bar] = field(default_factory=list)
    violations: list[ValidateViolation] = field(default_factory=list)


def _parse_date(value: JsonValue) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_row(row: JsonValue) -> Bar | str:
    """`row` convertie en `Bar` si elle a la forme `[date, 5 nombres, entier]`, sinon la raison.

    Aucune règle de contenu ici (prix > 0, OHLC…) : seulement la forme et les types.
    """
    if not isinstance(row, list):
        return f"ligne attendue sous forme de liste, reçu {type(row).__name__}"
    if len(row) != ROW_LENGTH:
        return f"{len(row)} éléments au lieu de {ROW_LENGTH}"
    day = _parse_date(row[0])
    if day is None:
        return f"date illisible {row[0]!r} (attendu AAAA-MM-JJ)"
    prices: list[float] = []
    for position, value in enumerate(row[1:6], start=1):
        if not isinstance(value, int | float) or isinstance(value, bool):
            return f"élément {position} : nombre attendu, reçu {value!r}"
        prices.append(float(value))
    volume = row[6]
    # `bool` est un sous-type d'`int` en Python : refusé explicitement.
    if not isinstance(volume, int) or isinstance(volume, bool):
        return f"volume : entier attendu, reçu {volume!r}"
    open_, high, low, close, adj_close = prices
    return (day, open_, high, low, close, adj_close, volume)


def check_rows(
    symbol: str,
    rows: Sequence[JsonValue],
    *,
    last_session: date,
    is_session: Callable[[date], bool],
) -> RowCheck:
    """Applique les règles bloquantes de F02 R2 à toutes les lignes de `bars`.

    Toutes les violations sont rapportées, y compris plusieurs sur une même ligne ; une ligne de
    forme invalide (`schema`) n'est pas examinée plus avant mais n'arrête pas les suivantes.
    `is_session` peut lever `ValueError` hors de la plage du calendrier : `non_session_date`.
    """
    violations: list[ValidateViolation] = []

    def report(day: date | None, rule: BlockingRule, detail: str) -> None:
        violations.append(ValidateViolation(symbol=symbol, date=day, rule=rule, detail=detail))

    if not rows:
        report(None, "empty_bars", "aucune barre")
        return RowCheck(violations=violations)

    bars: list[Bar] = []
    previous: date | None = None
    for row in rows:
        parsed = _parse_row(row)
        if isinstance(parsed, str):
            readable_day = _parse_date(row[0]) if isinstance(row, list) and row else None
            report(readable_day, "schema", parsed)
            continue
        day = parsed[0]
        where = day.isoformat()

        if previous is not None and day <= previous:
            report(
                day,
                "dates_not_increasing",
                f"{where} : date non strictement postérieure à {previous.isoformat()}",
            )
        previous = day if previous is None or day > previous else previous
        try:
            session = is_session(day)
        except ValueError:  # hors de la plage du calendrier
            session = False
        if not session:
            report(day, "non_session_date", f"{where} n'est pas une séance NYSE")
        if day > last_session:
            report(
                day,
                "after_last_session",
                f"{where} postérieure à la dernière séance clôturée {last_session.isoformat()}",
            )

        bars.append(parsed)

    return RowCheck(bars=[] if violations else bars, violations=violations)
