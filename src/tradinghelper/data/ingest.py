"""Orchestration de `th ingest` (F01). Toutes les dépendances (source, calendrier, horloge,
`sleep`, dossier) sont injectées : testable sans réseau ni attente réelle.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

# Attentes entre les tentatives : 1 tentative + 3 relances (R10).
RETRY_DELAYS: Final = (2.0, 4.0, 8.0)


class RetryError(Exception):
    """Toutes les tentatives d'un appel ont échoué (R10)."""

    def __init__(self, attempts: int, cause: Exception) -> None:
        self.attempts = attempts
        self.cause = cause
        super().__init__(f"échec après {attempts} tentatives : {cause}")


def with_retry[T](call: Callable[[], T], sleep: Callable[[float], None]) -> tuple[T, int]:
    """Exécute `call` en le relançant après 2 s, 4 s puis 8 s en cas d'exception.

    Renvoie `(résultat, nombre de tentatives)`. Lève `RetryError` (avec la dernière exception
    comme cause) après 4 échecs. Les interruptions (`KeyboardInterrupt`…) ne sont pas relancées.
    """
    attempts = 0
    while True:
        attempts += 1
        try:
            return call(), attempts
        except Exception as exc:
            if attempts > len(RETRY_DELAYS):
                raise RetryError(attempts, exc) from exc
            sleep(RETRY_DELAYS[attempts - 1])
