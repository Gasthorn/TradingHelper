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
from datetime import UTC
from pathlib import Path

from pydantic import JsonValue

from tradinghelper.schemas import Bar, PricesFile

ENCODING = "utf-8"


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
