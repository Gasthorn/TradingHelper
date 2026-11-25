"""Message de commit des workflows (F10 R5) : fonction pure, rapports construits en mémoire."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from tradinghelper.orchestration.commit_message import build_commit_message
from tradinghelper.schemas import IngestArgs, IngestRun, IngestTickerResult, RunReport

SESSION = date(2026, 11, 23)
FALLBACK = date(2026, 11, 24)
T0 = datetime(2026, 11, 23, 22, 31, 0, tzinfo=UTC)


def _ticker(symbol: str, *, rewritten: bool = False) -> IngestTickerResult:
    return IngestTickerResult(
        symbol=symbol,
        status="ok",
        mode="full" if rewritten else "incremental",
        bars_added=1,
        bars_revised=0,
        history_rewritten=rewritten,
        rewrite_reason="revision" if rewritten else None,
        attempts=1,
        error=None,
    )


def _run(started_at: datetime, *tickers: IngestTickerResult) -> IngestRun:
    return IngestRun(
        started_at=started_at,
        finished_at=started_at,
        duration_s=0.0,
        args=IngestArgs(symbols=None, full=False, start=None),
        exit_code=0,
        tickers=list(tickers),
        warnings=[],
    )


def _report(session: date, *runs: IngestRun) -> RunReport:
    return RunReport.model_validate(
        {
            "schema_version": 1,
            "session_date": session.isoformat(),
            "ingest": [run.model_dump(mode="json") for run in runs],
        }
    )


def _message(kind: str, *reports: RunReport) -> str:
    return build_commit_message(kind, list(reports), since=T0, fallback_session=FALLBACK)  # type: ignore[arg-type]


def test_daily_without_rewrite() -> None:
    report = _report(SESSION, _run(T0.replace(second=5), _ticker("AAPL")))

    assert _message("daily", report) == "data: daily update 2026-11-23"


def test_rewrite_symbols_sorted_deduplicated() -> None:
    report = _report(
        SESSION,
        _run(T0.replace(second=5), _ticker("MSFT", rewritten=True), _ticker("NVDA")),
        _run(
            T0.replace(minute=40), _ticker("AAPL", rewritten=True), _ticker("MSFT", rewritten=True)
        ),
    )

    assert (
        _message("daily", report) == "data: daily update 2026-11-23 (history rewrite: AAPL, MSFT)"
    )


def test_entries_before_since_ignored() -> None:
    earlier = _run(T0.replace(minute=10), _ticker("AAPL", rewritten=True))
    report = _report(SESSION, earlier, _run(T0.replace(minute=35), _ticker("MSFT")))

    assert _message("daily", report) == "data: daily update 2026-11-23"


def test_entry_at_since_included() -> None:
    report = _report(SESSION, _run(T0, _ticker("AAPL", rewritten=True)))

    assert _message("daily", report) == "data: daily update 2026-11-23 (history rewrite: AAPL)"


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("backfill", "data: backfill 2026-11-23 (history rewrite: AAPL)"),
        ("model", "model: weekly training 2026-11-23 (history rewrite: AAPL)"),
    ],
)
def test_backfill_and_model_prefixes(kind: str, expected: str) -> None:
    report = _report(SESSION, _run(T0, _ticker("AAPL", rewritten=True)))

    assert _message(kind, report) == expected


def test_fallback_session_without_recent_entry() -> None:
    old = _report(SESSION, _run(T0.replace(minute=0), _ticker("AAPL", rewritten=True)))
    no_ingest = RunReport.model_validate(
        {"schema_version": 1, "session_date": "2026-11-24", "validate": []}
    )

    assert _message("daily") == "data: daily update 2026-11-24"
    assert _message("daily", old, no_ingest) == "data: daily update 2026-11-24"


def test_session_of_most_recent_entry() -> None:
    first = _report(date(2026, 11, 20), _run(T0.replace(minute=50), _ticker("AAPL")))
    second = _report(SESSION, _run(T0.replace(minute=45), _ticker("MSFT")))

    assert _message("daily", second, first) == "data: daily update 2026-11-20"


def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="kind"):
        _message("weekly")


def test_naive_since_raises() -> None:
    with pytest.raises(ValueError, match="UTC"):
        build_commit_message("daily", [], since=T0.replace(tzinfo=None), fallback_session=FALLBACK)
