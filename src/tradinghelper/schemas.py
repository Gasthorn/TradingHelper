"""Contrats de données (source de vérité de `specs/03-data-contracts.md`).

`th schemas` génère les JSON Schemas de `schemas/` depuis ces modèles. Toute modification
de contrat incrémente `schema_version`, sauf l'ajout d'une section ou d'un champ optionnel qui
laisse valides les fichiers existants (contrats, en-tête).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    field_validator,
    model_validator,
)

from tradinghelper.config import Symbol

PRICE_DECIMALS: Final = 4

PRICE_COLUMNS: Final = ("date", "open", "high", "low", "close", "adj_close", "volume")


def _require_utc(value: datetime) -> datetime:
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError("horodatage attendu en UTC (suffixe Z)")
    return value


# Horodatage UTC ISO-8601 (CLAUDE.md : « UTC ISO-8601 pour les timestamps »).
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_require_utc)]

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
    last_updated: UtcDatetime
    bars: list[Bar]

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


# --- Rapport de run — `data/runs/{YYYY-MM-DD}.json` (contrat §6) --------------------------------

IngestStatus = Literal["ok", "unchanged", "failed"]
IngestMode = Literal["initial", "incremental", "full"]
RewriteReason = Literal["revision", "backfill"]
WarningRule = Literal[
    "nan",
    "non_session_date",
    "after_last_session",
    "non_positive_price",
    "negative_volume",
    "ohlc_inconsistent",
    "duplicate_date",
    "missing_overlap_bar",
]


class IngestTickerResult(_Contract):
    """Résultat de l'ingestion d'un symbole (F01 R15)."""

    symbol: Symbol
    status: IngestStatus
    mode: IngestMode | None  # None : aucun appel (ticker à jour, fichier corrompu)
    bars_added: NonNegativeInt
    bars_revised: NonNegativeInt
    history_rewritten: bool
    rewrite_reason: RewriteReason | None
    attempts: NonNegativeInt
    error: str | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.history_rewritten != (self.rewrite_reason is not None):
            raise ValueError(
                "rewrite_reason doit être renseignée si et seulement si history_rewritten"
            )
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("error doit être renseignée si et seulement si status == 'failed'")
        return self


class IngestWarning(_Contract):
    """Barre écartée ou anomalie non bloquante (F01 R3, R6)."""

    symbol: Symbol
    date: date | None
    rule: WarningRule


class IngestArgs(_Contract):
    """Arguments de `th ingest` journalisés (P4)."""

    symbols: list[Symbol] | None
    full: bool
    start: date | None


class IngestRun(_Contract):
    """Une exécution de `th ingest` (F01 R15)."""

    started_at: UtcDatetime
    finished_at: UtcDatetime
    duration_s: NonNegativeFloat
    args: IngestArgs
    exit_code: Literal[0, 1]
    tickers: list[IngestTickerResult]
    warnings: list[IngestWarning]

    @model_validator(mode="after")
    def _chronological(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at antérieur à started_at")
        return self


# --- Section `validate` du rapport de run (F02 R8) ----------------------------------------------

# Violations bloquantes (F02 R1, R2) : `th validate` sort en code 1.
BlockingRule = Literal[
    "unreadable",
    "schema",
    "symbol_mismatch",
    "empty_bars",
    "dates_not_increasing",
    "non_session_date",
    "after_last_session",
    "non_positive_price",
    "negative_volume",
    "ohlc_inconsistent",
    "not_rounded",
]

# Avertissements (F02 R3) : sans effet sur le code de sortie.
QualityWarningRule = Literal[
    "missing_session", "large_move", "zero_volume", "stale", "missing_file"
]

# Avertissements portant sur le fichier entier : ni `start` ni `end`.
UNDATED_WARNING_RULES: Final[frozenset[str]] = frozenset({"stale", "missing_file"})


class ValidateArgs(_Contract):
    """Arguments de `th validate` journalisés (P4)."""

    symbols: list[Symbol] | None
    all_history: bool


class ValidateViolation(_Contract):
    """Violation bloquante (F02 R1, R2). `symbol` est le nom du fichier sans `.json` : il peut
    ne pas être un symbole valide (fichier orphelin quelconque)."""

    symbol: str
    date: date | None  # None : erreur de fichier ou d'en-tête
    rule: BlockingRule
    detail: str


class ValidateWarning(_Contract):
    """Anomalie non bloquante (F02 R3), sur une barre (`start == end`) ou une plage de séances.

    `value` : variation simple pour `large_move`, nombre de séances pour `missing_session`
    et `stale` ; absente sinon.
    """

    symbol: Symbol
    rule: QualityWarningRule
    start: date | None
    end: date | None
    value: float | None = None

    @model_validator(mode="after")
    def _dates(self) -> Self:
        undated = self.rule in UNDATED_WARNING_RULES
        if undated and (self.start is not None or self.end is not None):
            raise ValueError(f"`{self.rule}` ne porte ni `start` ni `end`")
        if not undated:
            if self.start is None or self.end is None:
                raise ValueError(f"`{self.rule}` exige `start` et `end`")
            if self.start > self.end:
                raise ValueError("start postérieur à end")
        return self


class ValidateRun(_Contract):
    """Une exécution de `th validate` (F02 R8)."""

    started_at: UtcDatetime
    finished_at: UtcDatetime
    duration_s: NonNegativeFloat
    args: ValidateArgs
    exit_code: Literal[0, 1]
    files_checked: NonNegativeInt
    violations: list[ValidateViolation]
    warnings: list[ValidateWarning]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at antérieur à started_at")
        if (self.exit_code == 1) != bool(self.violations):
            raise ValueError("exit_code doit valoir 1 si et seulement s'il y a des violations")
        return self


class RunReport(BaseModel):
    """Rapport de run d'une séance. Chaque commande met à jour sa seule section ;
    les sections des features suivantes (ex. `signal`) sont conservées telles quelles.

    Sérialiser avec `by_alias=True` (clé JSON `validate`) et `exclude_unset=True` (une section
    absente du fichier n'y est pas ajoutée vide).
    """

    # `validate_by_name` : construction possible par `validate_=` comme par `validate=`.
    model_config = ConfigDict(
        extra="allow", frozen=True, validate_by_name=True, validate_by_alias=True
    )

    schema_version: Literal[1]
    session_date: date
    ingest: list[IngestRun] = Field(default_factory=list)
    # `validate` masquerait la méthode `BaseModel.validate` : champ Python `validate_`,
    # clé JSON `validate` (F02 R8).
    validate_: list[ValidateRun] = Field(default_factory=list, alias="validate")


# --- Signaux — `data/signals/{YYYY-MM-DD}.json` + `latest.json` (contrat §4) --------------------
# Définis par F08 (lecture des marqueurs dès M1), écrits par F07.

Action = Literal["BUY", "HOLD", "SELL"]

#: Nombre maximal de contributions expliquant un signal (contrat §4 : « top 5 »).
MAX_EXPLANATION: Final = 5

# Fraction dans [0, 1], finie.
UnitFloat = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class FeatureContribution(_Contract):
    """Contribution d'une feature à la prédiction (SHAP / gain)."""

    feature: str
    contribution: Annotated[float, Field(allow_inf_nan=False)]


class Signal(_Contract):
    """Signal d'une stratégie pour un symbole à une séance."""

    strategy_id: str
    symbol: Symbol
    action: Action
    confidence: UnitFloat
    target_weight: UnitFloat
    horizon_days: PositiveInt
    explanation: Annotated[list[FeatureContribution], Field(max_length=MAX_EXPLANATION)] | None = (
        None
    )


class SignalsFile(_Contract):
    """Signaux de toutes les stratégies actives pour une séance."""

    schema_version: Literal[1]
    date: date
    generated_at: UtcDatetime
    signals: list[Signal]


# --- Génération des JSON Schemas (`th schemas`) -------------------------------------------------

JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"

# Nom du contrat -> modèle ; fichier généré : `schemas/{nom}.schema.json`.
SCHEMA_MODELS: Final[dict[str, type[BaseModel]]] = {
    "prices": PricesFile,
    "run_report": RunReport,
}


def render_json_schemas() -> dict[str, str]:
    """Texte de chaque JSON Schema, par nom de fichier. Rendu déterministe :
    indentation 2, UTF-8 non échappé, fins de ligne LF, saut de ligne final."""
    rendered: dict[str, str] = {}
    for name, model in SCHEMA_MODELS.items():
        schema = {"$schema": JSON_SCHEMA_DIALECT, **model.model_json_schema()}
        rendered[f"{name}.schema.json"] = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    return rendered


def write_json_schemas(out_dir: Path) -> list[Path]:
    """Écrit les JSON Schemas dans `out_dir` (créé si besoin) ; renvoie les chemins écrits.

    Fichiers générés (pas des données) : écriture directe, ils sont régénérables à l'identique.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, text in render_json_schemas().items():
        path = out_dir / filename
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written
