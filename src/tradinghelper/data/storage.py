"""Stockage des données sur disque : effets de bord fichiers isolés ici (CLAUDE.md).

- Écriture atomique : fichier temporaire dans le même dossier puis `os.replace` (F01 R8, P7).
- Sérialisation canonique des prix (contrat §2) : une barre par ligne, déterministe octet pour
  octet, pour l'idempotence et des diffs git lisibles (P5).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import JsonValue, ValidationError

from tradinghelper.config import find_repo_root
from tradinghelper.schemas import PRICE_COLUMNS, Bar, IngestRun, PricesFile, RunReport, ValidateRun

ENCODING = "utf-8"

DATA_DIR_ENV = "TH_DATA_DIR"


# --- Emplacements ------------------------------------------------------------------------------


def data_dir() -> Path:
    """Dossier des données : `$TH_DATA_DIR` (si non vide) > `<racine du dépôt>/data`."""
    from_env = os.environ.get(DATA_DIR_ENV, "").strip()
    if from_env:
        return Path(from_env)
    return find_repo_root() / "data"


def prices_path(root: Path, symbol: str) -> Path:
    """`{root}/raw/prices/{SYMBOL}.json` — nom de fichier = symbole de config (F01 R12)."""
    return root / "raw" / "prices" / f"{symbol}.json"


def run_report_path(root: Path, session: date) -> Path:
    """`{root}/runs/{YYYY-MM-DD}.json`, nommé d'après la séance `S` (contrat §6)."""
    return root / "runs" / f"{session.isoformat()}.json"


# --- Écriture atomique -------------------------------------------------------------------------


def atomic_write_text(path: Path, text: str) -> None:
    """Écrit `text` (UTF-8, fins de ligne conservées telles quelles) de manière atomique.

    Le dossier parent est créé si besoin. En cas d'échec, le fichier existant est intact et
    le fichier temporaire est supprimé ; l'exception est propagée.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode(ENCODING))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def atomic_write_json(path: Path, data: JsonValue) -> None:
    """JSON indenté de 2 espaces, UTF-8 non échappé, saut de ligne final, écrit atomiquement."""
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _dumps_bar(bar: Bar) -> str:
    day, *prices, volume = bar
    # json.dumps(float) donne la représentation la plus courte (228.1, 231.0).
    values = [json.dumps(day.isoformat()), *(json.dumps(p) for p in prices), str(volume)]
    return "[" + ", ".join(values) + "]"


def dumps_prices(prices: PricesFile) -> str:
    """Sérialisation canonique d'un fichier de prix (contrat §2).

    Clés dans l'ordre du contrat, indentation 2, `columns` sur une ligne, une barre par ligne,
    `last_updated` en UTC à la seconde avec suffixe `Z`, LF, saut de ligne final.
    """
    last_updated = prices.last_updated.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = [
        f'  "schema_version": {prices.schema_version},',
        f'  "symbol": {json.dumps(prices.symbol)},',
        f'  "currency": {json.dumps(prices.currency)},',
        f'  "source": {json.dumps(prices.source)},',
        f'  "columns": [{", ".join(json.dumps(c) for c in prices.columns)}],',
        f'  "last_updated": {json.dumps(last_updated)},',
    ]
    if prices.bars:
        bars = ",\n".join(f"    {_dumps_bar(bar)}" for bar in prices.bars)
        body = f'  "bars": [\n{bars}\n  ]'
    else:
        body = '  "bars": []'
    return "{\n" + "\n".join(header) + "\n" + body + "\n}\n"


# --- Lecture et écriture des fichiers de prix --------------------------------------------------


class PricesFileError(Exception):
    """Fichier de prix illisible ou non conforme au contrat §2 (F01 R9)."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path.as_posix()}: {reason}")


def read_prices(path: Path) -> PricesFile | None:
    """Lit et valide un fichier de prix. `None` s'il n'existe pas ; `PricesFileError` s'il est
    illisible, n'est pas du JSON UTF-8 valide ou viole le contrat."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PricesFileError(path, f"fichier illisible ({exc.strerror})") from exc
    try:
        data = json.loads(raw.decode(ENCODING))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PricesFileError(path, f"JSON invalide ({exc})") from exc
    try:
        return PricesFile.model_validate(data)
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"])
        message = str(error["msg"]).removeprefix("Value error, ")
        raise PricesFileError(path, f"non conforme au contrat : {location}: {message}") from exc


def write_prices_if_changed(path: Path, symbol: str, bars: Sequence[Bar], now: datetime) -> bool:
    """Écrit `bars` (format canonique, atomique) sauf si le fichier contient déjà ces barres.

    `last_updated = now` seulement en cas d'écriture (F01 R8). Renvoie `True` si le fichier a
    été écrit. Un fichier existant illisible est remplacé : refuser de l'écraser (R9) est une
    décision de l'ingestion, prise avant d'appeler cette fonction. Lève `ValidationError`
    (une `ValueError`) si les barres violent le contrat ; rien n'est alors écrit.
    """
    with contextlib.suppress(PricesFileError):
        existing = read_prices(path)
        if existing is not None and existing.bars == list(bars):
            return False
    prices = PricesFile(
        schema_version=1,
        symbol=symbol,
        currency="USD",
        source="yfinance",
        columns=PRICE_COLUMNS,
        last_updated=now,
        bars=list(bars),
    )
    atomic_write_text(path, dumps_prices(prices))
    return True


# --- Rapport de run ----------------------------------------------------------------------------


class RunReportError(Exception):
    """Rapport de run existant illisible, non conforme ou d'une autre séance (contrat §6)."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path.as_posix()}: {reason}")


type ReportSection = Literal["ingest", "validate"]

# Type d'entrée attendu par section : une entrée n'est jamais rangée dans la mauvaise section.
_SECTION_ENTRY: Final[dict[str, type[IngestRun | ValidateRun]]] = {
    "ingest": IngestRun,
    "validate": ValidateRun,
}


def update_run_report(path: Path, session: date, run: IngestRun) -> None:
    """Ajoute `run` à la section `ingest` du rapport de la séance `session` (F01 R15)."""
    append_run_report_entry(path, session, "ingest", run)


def append_run_report_entry(
    path: Path, session: date, section: ReportSection, entry: IngestRun | ValidateRun
) -> None:
    """Ajoute `entry` à la liste `section` du rapport de la séance `session` (F01 R15, F02 R7).

    Le fichier est créé s'il n'existe pas, avec la seule section concernée. Les autres sections
    sont conservées telles quelles ; une section absente du fichier n'y est pas ajoutée vide.
    Un rapport existant illisible, non conforme ou d'une autre séance n'est jamais écrasé (P7) :
    `RunReportError`. Écriture atomique.
    """
    expected = _SECTION_ENTRY[section]
    if not isinstance(entry, expected):
        raise TypeError(f"section `{section}` : {expected.__name__} attendu")
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raw = None
    except OSError as exc:
        raise RunReportError(path, f"fichier illisible ({exc.strerror})") from exc

    if raw is None:
        current: dict[str, JsonValue] = {
            "schema_version": 1,
            "session_date": session.isoformat(),
        }
    else:
        try:
            existing = RunReport.model_validate_json(raw)
        except ValidationError as exc:
            raise RunReportError(path, f"rapport invalide : {exc.errors()[0]['msg']}") from exc
        if existing.session_date != session:
            raise RunReportError(
                path,
                f"séance {existing.session_date.isoformat()} dans le fichier, "
                f"{session.isoformat()} attendue",
            )
        # Clé JSON `validate` (alias) ; une section absente du fichier n'y est pas ajoutée.
        current = existing.model_dump(mode="json", by_alias=True, exclude_unset=True)

    previous = current.get(section)
    entries = list(previous) if isinstance(previous, list) else []
    entries.append(entry.model_dump(mode="json"))
    current[section] = entries
    # Validation du résultat avant écriture : on n'écrit jamais un rapport hors contrat.
    RunReport.model_validate(current)
    atomic_write_json(path, current)
