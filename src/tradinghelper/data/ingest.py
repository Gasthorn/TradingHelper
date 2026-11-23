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
from tradinghelper.data.bars import (
    OVERLAP_SESSIONS,
    Cleaned,
    clean_bars,
    merge_overlap,
    needs_rewrite,
)
from tradinghelper.data.calendar import NyseCalendar
from tradinghelper.data.source import PriceSource, RawBar
from tradinghelper.data.storage import (
    PricesFileError,
    prices_path,
    read_prices,
    write_prices_if_changed,
)
from tradinghelper.schemas import (
    Bar,
    IngestArgs,
    IngestMode,
    IngestRun,
    IngestTickerResult,
    IngestWarning,
    PricesFile,
    RewriteReason,
)

# Attentes entre les tentatives : 1 tentative + 3 relances (R10).
RETRY_DELAYS: Final = (2.0, 4.0, 8.0)

# Nombre maximal de tickers par appel groupé à la source (R11).
BATCH_SIZE: Final = 20


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


def _select(
    targets: list[tuple[str, date]], symbols: tuple[str, ...] | None
) -> list[tuple[str, date]]:
    """Restreint la cible à `symbols` (ordre de l'univers) ; symbole inconnu : `ValueError`
    (la CLI le vérifie avant, R13)."""
    if symbols is None:
        return targets
    known = {symbol for symbol, _ in targets}
    unknown = [symbol for symbol in symbols if symbol not in known]
    if unknown:
        raise ValueError(f"symboles hors univers et hors benchmark : {', '.join(unknown)}")
    wanted = set(symbols)
    return [(symbol, start) for symbol, start in targets if symbol in wanted]


@dataclass(frozen=True)
class _Plan:
    """Ticker à télécharger."""

    symbol: str
    mode: IngestMode
    fetch_start: date
    stored: PricesFile | None
    start: date  # `start` de l'univers (borne d'une réécriture complète, R4)


def _result(
    symbol: str,
    status: Literal["ok", "unchanged", "failed"],
    mode: IngestMode | None,
    *,
    attempts: int = 0,
    bars_added: int = 0,
    bars_revised: int = 0,
    rewrite_reason: RewriteReason | None = None,
    error: str | None = None,
) -> IngestTickerResult:
    return IngestTickerResult(
        symbol=symbol,
        status=status,
        mode=mode,
        bars_added=bars_added,
        bars_revised=bars_revised,
        history_rewritten=rewrite_reason is not None,
        rewrite_reason=rewrite_reason,
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

    def plan(self, symbol: str, start: date, request: IngestRequest) -> _Plan | IngestTickerResult:
        try:
            stored = read_prices(prices_path(self.data_root, symbol))
        except PricesFileError as exc:
            if not request.full:
                # R9 : un fichier illisible n'est jamais écrasé par un run ordinaire.
                return _result(
                    symbol,
                    "failed",
                    None,
                    error=f"{exc} — réparer avec `th ingest --symbols {symbol} --full`",
                )
            stored = None  # le backfill `--full` est le moyen de le réparer (R13)
        if request.full:
            full_start = request.start or start
            if full_start > self.session:
                return _result(symbol, "unchanged", None)
            return _Plan(symbol, "full", full_start, stored, start)
        if stored is None or not stored.bars:
            if start > self.session:
                return _result(symbol, "unchanged", None)
            return _Plan(symbol, "initial", start, stored, start)
        last = stored.bars[-1][0]
        if last >= self.session:
            return _result(symbol, "unchanged", None)
        since = self.calendar.shift(last, -OVERLAP_SESSIONS)
        return _Plan(symbol, "incremental", since, stored, start)

    def fetch_one(self, symbol: str, start: date, prior_attempts: int = 0) -> _Fetched:
        """Appel individuel avec relances ; `prior_attempts` : tentatives déjà faites en lot."""
        try:
            response, attempts = with_retry(
                partial(self.source.fetch, [symbol], start, self.session), self.sleep
            )
        except RetryError as exc:
            return _Fetched(None, prior_attempts + exc.attempts, str(exc))
        bars = response.get(symbol)
        if bars is None:
            return _Fetched(None, prior_attempts + attempts, "aucune donnée renvoyée")
        return _Fetched(bars, prior_attempts + attempts)

    def fetch(self, plans: Sequence[_Plan]) -> Mapping[str, _Fetched]:
        """Lots de ≤ 20 tickers de même date de début (R11) ; un ticker absent de la réponse
        d'un lot, ou d'un lot en échec, est retenté seul. `attempts` compte tous les appels
        (groupés et individuels) où le ticker figurait."""
        by_start: dict[date, list[str]] = {}
        for plan in plans:
            by_start.setdefault(plan.fetch_start, []).append(plan.symbol)

        fetched: dict[str, _Fetched] = {}
        for start, symbols in by_start.items():
            for offset in range(0, len(symbols), BATCH_SIZE):
                batch = symbols[offset : offset + BATCH_SIZE]
                try:
                    response, attempts = with_retry(
                        partial(self.source.fetch, batch, start, self.session), self.sleep
                    )
                except RetryError as exc:
                    response, attempts = {}, exc.attempts
                for symbol in batch:
                    bars = response.get(symbol)
                    fetched[symbol] = (
                        _Fetched(bars, attempts)
                        if bars is not None
                        else self.fetch_one(symbol, start, prior_attempts=attempts)
                    )
        return fetched

    def process(self, plan: _Plan, fetched: _Fetched) -> IngestTickerResult:
        if fetched.bars is None:
            return _result(
                plan.symbol, "failed", plan.mode, attempts=fetched.attempts, error=fetched.error
            )
        cleaned = self.clean(plan.symbol, fetched.bars)
        if plan.mode == "incremental":
            return self.incremental(plan, fetched.attempts, cleaned)
        self.warnings.extend(cleaned.warnings)
        if not cleaned.bars:
            return _result(
                plan.symbol,
                "failed",
                plan.mode,
                attempts=fetched.attempts,
                error="aucune barre valide dans la réponse",
            )
        self.write(plan.symbol, cleaned.bars)
        old = {bar[0]: bar for bar in plan.stored.bars} if plan.stored is not None else {}
        return _result(
            plan.symbol,
            "ok",
            plan.mode,
            attempts=fetched.attempts,
            bars_added=sum(1 for bar in cleaned.bars if bar[0] not in old),
            bars_revised=sum(1 for bar in cleaned.bars if bar[0] in old and old[bar[0]] != bar),
            rewrite_reason="backfill" if plan.mode == "full" else None,
        )

    def clean(self, symbol: str, raw: Sequence[RawBar]) -> Cleaned:
        return clean_bars(
            symbol, raw, last_session=self.session, is_session=self.calendar.is_session
        )

    def write(self, symbol: str, bars: Sequence[Bar]) -> None:
        path = prices_path(self.data_root, symbol)
        self.changed |= write_prices_if_changed(path, symbol, bars, self.now())

    def incremental(self, plan: _Plan, attempts: int, cleaned: Cleaned) -> IngestTickerResult:
        """Mode incrémental (R3) : fusion du recouvrement, ou réécriture complète si l'historique
        ajusté a changé (R4). Les avertissements ne sont retenus que pour la réponse utilisée."""
        assert plan.stored is not None
        stored = plan.stored.bars
        last = stored[-1][0]
        if not any(bar[0] > last for bar in cleaned.bars):
            self.warnings.extend(cleaned.warnings)
            return _result(
                plan.symbol,
                "failed",
                "incremental",
                attempts=attempts,
                error=f"aucune barre pour des séances attendues après {last.isoformat()}",
            )
        if needs_rewrite(stored, cleaned.bars, since=plan.fetch_start):
            return self.rewrite(plan, attempts)
        merge = merge_overlap(plan.symbol, stored, cleaned.bars, since=plan.fetch_start)
        self.warnings.extend([*cleaned.warnings, *merge.warnings])
        self.write(plan.symbol, merge.bars)
        return _result(
            plan.symbol,
            "ok",
            "incremental",
            attempts=attempts,
            bars_added=merge.added,
            bars_revised=merge.revised,
        )

    def rewrite(self, plan: _Plan, attempts: int) -> IngestTickerResult:
        """Réécriture complète sur révision (R4) : un seul re-téléchargement, depuis
        `min(start de l'univers, première date stockée)` ; en cas d'échec, fichier intact."""
        assert plan.stored is not None
        stored = plan.stored.bars
        full_start = min(plan.start, stored[0][0])
        refetched = self.fetch_one(plan.symbol, full_start, prior_attempts=attempts)
        if refetched.bars is None:
            return _result(
                plan.symbol,
                "failed",
                "incremental",
                attempts=refetched.attempts,
                error=f"révision détectée, réécriture complète impossible : {refetched.error}",
            )
        cleaned = self.clean(plan.symbol, refetched.bars)
        self.warnings.extend(cleaned.warnings)
        if not cleaned.bars:
            return _result(
                plan.symbol,
                "failed",
                "incremental",
                attempts=refetched.attempts,
                error="révision détectée, réécriture complète sans barre valide",
            )
        old = {bar[0]: bar for bar in stored}
        last = stored[-1][0]
        self.write(plan.symbol, cleaned.bars)
        return _result(
            plan.symbol,
            "ok",
            "incremental",
            attempts=refetched.attempts,
            bars_added=sum(1 for bar in cleaned.bars if bar[0] > last),
            bars_revised=sum(1 for bar in cleaned.bars if bar[0] in old and old[bar[0]] != bar),
            rewrite_reason="revision",
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
        run.plan(symbol, start, request)
        for symbol, start in _select(_targets(universe), request.symbols)
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
