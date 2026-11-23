"""Orchestration de `th ingest` (F01). Toutes les dépendances (source, calendrier, horloge,
`sleep`, dossier) sont injectées : testable sans réseau ni attente réelle.

Un run se déroule en trois phases :
1. planification par ticker (fichier lu, mode choisi, ou résultat immédiat : à jour, corrompu) ;
2. téléchargement des tickers à mettre à jour, avec relances (R10) ;
3. traitement : nettoyage (R6), écriture atomique et canonique (R8), résultat par ticker.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import partial
from pathlib import Path
from typing import Final, Literal

from tradinghelper.config import UniverseConfig
from tradinghelper.data.bars import OVERLAP_SESSIONS, clean_bars
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.source import PriceSource, RawBar
from tradinghelper.data.storage import (
    PricesFileError,
    prices_path,
    read_prices,
    write_prices_if_changed,
)
from tradinghelper.schemas import (
    IngestArgs,
    IngestMode,
    IngestRun,
    IngestTickerResult,
    IngestWarning,
    PricesFile,
)

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


# --- Requête et résultat -----------------------------------------------------------------------


@dataclass(frozen=True)
class IngestRequest:
    """Arguments de `th ingest` (R13), déjà validés par la CLI."""

    symbols: tuple[str, ...] | None = None
    full: bool = False
    start: date | None = None


@dataclass(frozen=True)
class IngestOutcome:
    run: IngestRun
    session: date  # S, dernière séance clôturée : nom du rapport (contrat §6)
    changed: bool  # au moins un fichier de prix écrit

    @property
    def should_report(self) -> bool:
        """Rapport écrit seulement s'il y a quelque chose à signaler (R15)."""
        return self.changed or any(t.status == "failed" for t in self.run.tickers)


def exit_code(results: Sequence[IngestTickerResult]) -> Literal[0, 1]:
    """1 si au moins un ticker a été tenté (≥ 1 appel) et que tous les tentés ont échoué (R14)."""
    attempted = [r for r in results if r.attempts > 0]
    return 1 if attempted and all(r.status == "failed" for r in attempted) else 0


# --- Planification -----------------------------------------------------------------------------


def _targets(universe: UniverseConfig) -> list[tuple[str, date]]:
    """Tickers de l'univers puis benchmark (`start` = plus ancien `start`, R1), sans doublon."""
    targets = [(t.symbol, t.start) for t in universe.tickers]
    if universe.benchmark not in {symbol for symbol, _ in targets}:
        targets.append((universe.benchmark, min(start for _, start in targets)))
    return targets


@dataclass(frozen=True)
class _Plan:
    """Ticker à télécharger."""

    symbol: str
    mode: IngestMode
    fetch_start: date
    stored: PricesFile | None


def _result(
    symbol: str,
    status: Literal["ok", "unchanged", "failed"],
    mode: IngestMode | None,
    *,
    attempts: int = 0,
    bars_added: int = 0,
    bars_revised: int = 0,
    error: str | None = None,
) -> IngestTickerResult:
    return IngestTickerResult(
        symbol=symbol,
        status=status,
        mode=mode,
        bars_added=bars_added,
        bars_revised=bars_revised,
        history_rewritten=False,
        rewrite_reason=None,
        attempts=attempts,
        error=error,
    )


# --- Exécution ---------------------------------------------------------------------------------


@dataclass
class _Fetched:
    bars: list[RawBar] | None
    attempts: int
    error: str | None = None


class _Ingestion:
    def __init__(
        self,
        *,
        source: PriceSource,
        calendar: NyseCalendar,
        now: Callable[[], datetime],
        sleep: Callable[[float], None],
        data_root: Path,
        session: date,
    ) -> None:
        self.source = source
        self.calendar = calendar
        self.now = now
        self.sleep = sleep
        self.data_root = data_root
        self.session = session
        self.warnings: list[IngestWarning] = []
        self.changed = False

    def plan(self, symbol: str, start: date) -> _Plan | IngestTickerResult:
        try:
            stored = read_prices(prices_path(self.data_root, symbol))
        except PricesFileError as exc:
            # R9 : un fichier illisible n'est jamais écrasé par un run ordinaire.
            return _result(
                symbol,
                "failed",
                None,
                error=f"{exc} — réparer avec `th ingest --symbols {symbol} --full`",
            )
        if stored is None or not stored.bars:
            if start > self.session:
                return _result(symbol, "unchanged", None)
            return _Plan(symbol, "initial", start, stored)
        last = stored.bars[-1][0]
        if last >= self.session:
            return _result(symbol, "unchanged", None)
        return _Plan(symbol, "incremental", self.calendar.shift(last, -OVERLAP_SESSIONS), stored)

    def fetch(self, plans: Sequence[_Plan]) -> Mapping[str, _Fetched]:
        fetched: dict[str, _Fetched] = {}
        for plan in plans:
            try:
                response, attempts = with_retry(
                    partial(self.source.fetch, [plan.symbol], plan.fetch_start, self.session),
                    self.sleep,
                )
            except RetryError as exc:
                fetched[plan.symbol] = _Fetched(None, exc.attempts, str(exc))
                continue
            bars = response.get(plan.symbol)
            if bars is None:
                fetched[plan.symbol] = _Fetched(None, attempts, "aucune donnée renvoyée")
            else:
                fetched[plan.symbol] = _Fetched(bars, attempts)
        return fetched

    def process(self, plan: _Plan, fetched: _Fetched) -> IngestTickerResult:
        if fetched.bars is None:
            return _result(
                plan.symbol, "failed", plan.mode, attempts=fetched.attempts, error=fetched.error
            )
        cleaned = clean_bars(
            plan.symbol,
            fetched.bars,
            last_session=self.session,
            is_session=self.calendar.is_session,
        )
        self.warnings.extend(cleaned.warnings)
        if plan.mode == "incremental":
            raise NotImplementedError("mode incrémental : T15")
        if not cleaned.bars:
            return _result(
                plan.symbol,
                "failed",
                plan.mode,
                attempts=fetched.attempts,
                error="aucune barre valide dans la réponse",
            )
        written = write_prices_if_changed(
            prices_path(self.data_root, plan.symbol), plan.symbol, cleaned.bars, self.now()
        )
        self.changed |= written
        return _result(
            plan.symbol,
            "ok",
            plan.mode,
            attempts=fetched.attempts,
            bars_added=len(cleaned.bars),
        )


def ingest(
    universe: UniverseConfig,
    request: IngestRequest,
    *,
    source: PriceSource,
    calendar: NyseCalendar,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    data_root: Path,
) -> IngestOutcome:
    """Exécute un run d'ingestion et renvoie son résultat (le rapport est écrit par la CLI)."""
    started_at = now()
    session = calendar.last_closed_session(started_at)
    run = _Ingestion(
        source=source,
        calendar=calendar,
        now=now,
        sleep=sleep,
        data_root=data_root,
        session=session,
    )

    planned: list[_Plan | IngestTickerResult] = [
        run.plan(symbol, start) for symbol, start in _targets(universe)
    ]
    fetched = run.fetch([p for p in planned if isinstance(p, _Plan)])
    results = [run.process(p, fetched[p.symbol]) if isinstance(p, _Plan) else p for p in planned]

    finished_at = now()
    return IngestOutcome(
        run=IngestRun(
            started_at=started_at,
            finished_at=finished_at,
            duration_s=(finished_at - started_at).total_seconds(),
            args=IngestArgs(
                symbols=list(request.symbols) if request.symbols is not None else None,
                full=request.full,
                start=request.start,
            ),
            exit_code=exit_code(results),
            tickers=results,
            warnings=run.warnings,
        ),
        session=session,
        changed=run.changed,
    )
