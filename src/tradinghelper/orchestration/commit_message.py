"""Message de commit des workflows qui écrivent des données (F10 R5).

Fonction pure : les rapports de run sont lus par l'appelant (`storage.read_run_reports`) et la
séance de repli `S` lui est fournie. Le message journalise les réécritures d'historique du run
courant, comme l'exige P5 (F01 R4).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Final, Literal, get_args

from tradinghelper.schemas import IngestRun, RunReport

type CommitKind = Literal["daily", "backfill", "model"]

PREFIX: Final[dict[CommitKind, str]] = {
    "daily": "data: daily update",
    "backfill": "data: backfill",
    "model": "model: weekly training",
}


def build_commit_message(
    kind: CommitKind,
    reports: Sequence[RunReport],
    *,
    since: datetime,
    fallback_session: date,
) -> str:
    """Message `<préfixe> <D>[ (history rewrite: A, B)]`.

    Seules comptent les entrées `ingest` démarrées à `since` (T0, UTC) ou après : celles d'un run
    antérieur de la même séance sont ignorées. `D` est la séance du rapport contenant l'entrée
    retenue la plus récente ; sans entrée retenue, `fallback_session`.
    """
    if kind not in get_args(CommitKind.__value__):
        raise ValueError(f"kind inconnu : {kind!r}")
    if since.utcoffset() != timedelta(0):
        raise ValueError("since doit être un horodatage UTC")

    recent: list[tuple[IngestRun, date]] = [
        (run, report.session_date)
        for report in reports
        for run in report.ingest
        if run.started_at >= since
    ]
    latest = max(recent, key=lambda item: item[0].started_at, default=None)
    session = latest[1] if latest is not None else fallback_session
    rewritten = sorted(
        {ticker.symbol for run, _ in recent for ticker in run.tickers if ticker.history_rewritten}
    )

    message = f"{PREFIX[kind]} {session.isoformat()}"
    if rewritten:
        message += f" (history rewrite: {', '.join(rewritten)})"
    return message
