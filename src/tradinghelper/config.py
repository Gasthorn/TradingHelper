"""Chargement et validation de la configuration (`config/*.yaml`).

Aucun appel réseau ici (R9) : la validation porte uniquement sur le contenu des fichiers.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    NonNegativeFloat,
    PositiveFloat,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from yaml.nodes import MappingNode

SYMBOL_PATTERN = r"^[A-Z][A-Z0-9.\-]{0,9}$"

CONFIG_FILES = ("universe.yaml", "backtest.yaml", "strategies.yaml")
CONFIG_DIR_ENV = "TH_CONFIG_DIR"

Symbol = Annotated[str, StringConstraints(pattern=SYMBOL_PATTERN)]


class ConfigError(Exception):
    """Erreur de configuration lisible : fichier + champ + raison (R8)."""

    def __init__(self, file: Path, field: str | None, reason: str) -> None:
        self.file = file
        self.field = field
        self.reason = reason
        # as_posix : message identique sous Windows et en CI Linux.
        location = f"{file.as_posix()}: {field}" if field else file.as_posix()
        super().__init__(f"{location}: {reason}")


class _DuplicateKeyError(yaml.YAMLError):
    def __init__(self, key: str, line: int) -> None:
        super().__init__(key)
        self.key = key
        self.line = line


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader qui refuse les clés dupliquées (PyYAML garde sinon la dernière en silence)."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise _DuplicateKeyError(str(key), key_node.start_mark.line + 1)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _read_yaml(path: Path) -> dict[str, object]:
    """Lit un fichier YAML dont la racine doit être un mapping non vide.

    Lève `ConfigError` si le fichier est absent, vide, mal formé, a une clé dupliquée,
    ou si sa racine n'est pas un mapping.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(path, None, "fichier introuvable") from None

    try:
        data = yaml.load(text, Loader=_StrictLoader)  # _StrictLoader dérive de SafeLoader
    except _DuplicateKeyError as exc:
        raise ConfigError(path, exc.key, f"clé dupliquée (ligne {exc.line})") from None
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (ligne {mark.line + 1})" if mark is not None else ""
        raise ConfigError(path, None, f"YAML invalide{where}") from None

    if data is None:
        raise ConfigError(path, None, "fichier vide")
    if not isinstance(data, dict):
        raise ConfigError(path, None, f"la racine doit être un mapping, pas {type(data).__name__}")
    return {str(k): v for k, v in data.items()}


# --- Modèles ------------------------------------------------------------------------------------


class _Strict(BaseModel):
    """Base commune : clés inconnues refusées (R8), objets immuables."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class TickerConfig(_Strict):
    symbol: Symbol
    name: str
    sector: str
    start: date

    @field_validator("start")
    @classmethod
    def _start_not_in_future(cls, value: date, info: ValidationInfo) -> date:
        context = info.context if isinstance(info.context, dict) else {}
        today = context.get("today", date.today())
        if value > today:
            raise ValueError(f"date de début {value.isoformat()} postérieure à aujourd'hui")
        return value


class UniverseConfig(_Strict):
    currency: Literal["USD"]  # v1 : USD uniquement (vision)
    benchmark: Symbol
    tickers: Annotated[list[TickerConfig], Field(min_length=1)]

    @field_validator("tickers")
    @classmethod
    def _unique_symbols(cls, tickers: list[TickerConfig]) -> list[TickerConfig]:
        first_index: dict[str, int] = {}
        for index, ticker in enumerate(tickers):
            key = ticker.symbol.casefold()
            if key in first_index:
                raise ValueError(
                    f"symbole dupliqué {ticker.symbol!r} (positions {first_index[key]} et {index})"
                )
            first_index[key] = index
        return tickers


class BacktestConfig(_Strict):
    """Clés minimales ; leur sémantique est définie par F04 (R3)."""

    initial_capital: PositiveFloat
    commission_fixed: NonNegativeFloat  # USD par ordre
    commission_pct: NonNegativeFloat  # fraction du notionnel
    slippage_bps: NonNegativeFloat


class StrategyEntry(_Strict):
    id: str
    type: str
    active: bool = True
    params: dict[str, JsonValue] = Field(default_factory=dict)


class StrategiesConfig(_Strict):
    """Structure minimale ; les entrées sont ajoutées par F05 et F06."""

    strategies: list[StrategyEntry]

    @field_validator("strategies")
    @classmethod
    def _unique_ids(cls, strategies: list[StrategyEntry]) -> list[StrategyEntry]:
        first_index: dict[str, int] = {}
        for index, entry in enumerate(strategies):
            if entry.id in first_index:
                raise ValueError(
                    f"id de stratégie dupliqué {entry.id!r} "
                    f"(positions {first_index[entry.id]} et {index})"
                )
            first_index[entry.id] = index
        return strategies


class AppConfig(_Strict):
    config_dir: Path
    universe: UniverseConfig
    backtest: BacktestConfig
    strategies: StrategiesConfig


# --- Validation ---------------------------------------------------------------------------------


def _format_loc(loc: tuple[int | str, ...]) -> str | None:
    """('tickers', 3, 'symbol') -> 'tickers[3].symbol'."""
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else part)
    return out or None


def _validate[M: BaseModel](model: type[M], data: object, file: Path, today: date) -> M:
    """Valide `data` contre `model` ; convertit la 1re erreur pydantic en `ConfigError`."""
    try:
        return model.model_validate(data, context={"today": today})
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        reason = str(error["msg"]).removeprefix("Value error, ")
        raise ConfigError(file, _format_loc(tuple(error["loc"])), reason) from None


# --- Résolution du dossier (R7) -----------------------------------------------------------------


def find_repo_root(start: Path | None = None) -> Path:
    """Remonte depuis `start` (défaut : répertoire courant) jusqu'au dossier contenant
    `pyproject.toml`. Lève `ConfigError` si aucun n'est trouvé."""
    origin = (start if start is not None else Path.cwd()).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise ConfigError(origin, None, "aucun pyproject.toml trouvé : racine du dépôt introuvable")


def resolve_config_dir(config_dir: Path | None = None) -> Path:
    """Dossier de config : argument > `$TH_CONFIG_DIR` (si non vide) > `<racine>/config`."""
    if config_dir is not None:
        return config_dir
    from_env = os.environ.get(CONFIG_DIR_ENV, "").strip()
    if from_env:
        return Path(from_env)
    return find_repo_root() / "config"


# --- Chargement ---------------------------------------------------------------------------------


def load_config(config_dir: Path | None = None, *, today: date | None = None) -> AppConfig:
    """Charge et valide `universe.yaml`, `backtest.yaml` et `strategies.yaml`.

    `today` est injectable pour les tests (défaut : `date.today()`).
    Lève `ConfigError` à la première erreur rencontrée.
    """
    directory = resolve_config_dir(config_dir)
    reference = today if today is not None else date.today()

    def _load[M: BaseModel](model: type[M], filename: str) -> M:
        path = directory / filename
        return _validate(model, _read_yaml(path), path, reference)

    return AppConfig(
        config_dir=directory,
        universe=_load(UniverseConfig, "universe.yaml"),
        backtest=_load(BacktestConfig, "backtest.yaml"),
        strategies=_load(StrategiesConfig, "strategies.yaml"),
    )
