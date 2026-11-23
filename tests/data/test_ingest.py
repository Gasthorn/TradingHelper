"""Tests de l'orchestration de l'ingestion (F01). Aucun réseau : `FakePriceSource`,
vrai calendrier NYSE (hors ligne), horloge et `sleep` injectés."""

from __future__ import annotations

import pytest

from fakes import RecordingSleep
from tradinghelper.data.ingest import RETRY_DELAYS, RetryError, with_retry

# --- Relances avec backoff (R10) ---------------------------------------------------------------


class _Flaky:
    """Appel qui lève `failures` fois puis renvoie `"ok"`."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError(f"échec n°{self.calls}")
        return "ok"


def test_retry_delays_are_2_4_8() -> None:
    assert RETRY_DELAYS == (2.0, 4.0, 8.0)


def test_with_retry_first_try() -> None:
    sleep = RecordingSleep()
    call = _Flaky(0)

    assert with_retry(call, sleep) == ("ok", 1)
    assert sleep.delays == []
    assert call.calls == 1


def test_with_retry_succeeds_after_two_failures() -> None:
    sleep = RecordingSleep()
    call = _Flaky(2)

    assert with_retry(call, sleep) == ("ok", 3)
    assert sleep.delays == [2.0, 4.0]


def test_with_retry_succeeds_on_last_attempt() -> None:
    sleep = RecordingSleep()

    assert with_retry(_Flaky(3), sleep) == ("ok", 4)
    assert sleep.delays == [2.0, 4.0, 8.0]


def test_with_retry_gives_up_after_four_attempts() -> None:
    sleep = RecordingSleep()
    call = _Flaky(10)

    with pytest.raises(RetryError) as excinfo:
        with_retry(call, sleep)

    assert call.calls == 4
    assert sleep.delays == [2.0, 4.0, 8.0]
    assert excinfo.value.attempts == 4
    assert isinstance(excinfo.value.cause, ConnectionError)
    assert str(excinfo.value.cause) == "échec n°4"
    assert excinfo.value.__cause__ is excinfo.value.cause
    assert "échec n°4" in str(excinfo.value)


def test_with_retry_does_not_swallow_interrupts() -> None:
    sleep = RecordingSleep()

    def interrupted() -> str:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        with_retry(interrupted, sleep)
    assert sleep.delays == []
