"""Tests des contrats de données (F01 — R17, R8, R15 ; contrats §2 et §6)."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from tradinghelper.cli import app
from tradinghelper.schemas import (
    PRICE_COLUMNS,
    SCHEMA_MODELS,
    SPARK_LENGTH,
    ExportSignal,
    IngestTickerResult,
    IngestWarning,
    OverviewFile,
    PricesFile,
    RunReport,
    Signal,
    SignalsFile,
    TickerFile,
    TickerSeries,
    ValidateRun,
    ValidateViolation,
    ValidateWarning,
    render_json_schemas,
    write_json_schemas,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = REPO_ROOT / "specs" / "03-data-contracts.md"


def _valid_prices() -> dict[str, Any]:
    """Fichier de prix valide, sous la forme JSON du contrat §2."""
    return {
        "schema_version": 1,
        "symbol": "AAPL",
        "currency": "USD",
        "source": "yfinance",
        "columns": list(PRICE_COLUMNS),
        "last_updated": "2026-11-23T22:41:05Z",
        "bars": [
            ["2026-11-20", 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000],
            ["2026-11-23", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000],
        ],
    }


def _with(**changes: Any) -> dict[str, Any]:
    data = _valid_prices()
    data.update(copy.deepcopy(changes))
    return data


def _without(key: str) -> dict[str, Any]:
    data = _valid_prices()
    del data[key]
    return data


def _with_bar(index: int, position: int, value: Any) -> dict[str, Any]:
    data = _valid_prices()
    data["bars"][index][position] = value
    return data


def test_price_columns_match_contract() -> None:
    assert PRICE_COLUMNS == ("date", "open", "high", "low", "close", "adj_close", "volume")


def test_prices_model_accepts_valid_file() -> None:
    prices = PricesFile.model_validate(_valid_prices())

    assert prices.symbol == "AAPL"
    assert len(prices.bars) == 2
    assert prices.bars[0][0].isoformat() == "2026-11-20"
    assert prices.bars[1][6] == 48765000
    assert prices.last_updated.utcoffset() is not None
    assert prices.last_updated.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_prices_model_accepts_empty_bars() -> None:
    assert PricesFile.model_validate(_with(bars=[])).bars == []


INVALID_CASES: dict[str, tuple[dict[str, Any], str]] = {
    "dates non croissantes": (
        _with(
            bars=[
                ["2026-11-23", 231.0, 233.12, 229.6, 232.4, 231.1734, 48765000],
                ["2026-11-20", 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000],
            ]
        ),
        "2026-11-20",
    ),
    "date dupliquée": (
        _with(
            bars=[
                ["2026-11-20", 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000],
                ["2026-11-20", 228.1, 231.45, 227.8, 230.95, 229.7312, 51234000],
            ]
        ),
        "2026-11-20",
    ),
    "prix nul": (_with_bar(0, 1, 0.0), "bars"),
    "prix négatif": (_with_bar(0, 5, -1.0), "bars"),
    "prix NaN": (_with_bar(0, 4, float("nan")), "bars"),
    "prix non arrondi à 4 décimales": (_with_bar(0, 4, 230.95001), "2026-11-20"),
    "low > open": (_with_bar(0, 3, 228.2), "2026-11-20"),
    "low > close": (_with_bar(1, 3, 232.5), "2026-11-23"),
    "high < open": (_with_bar(1, 2, 230.0), "2026-11-23"),
    "high < close": (_with_bar(0, 2, 230.0), "2026-11-20"),
    "volume négatif": (_with_bar(0, 6, -1), "bars"),
    "volume non entier": (_with_bar(0, 6, 1.5), "bars"),
    "barre trop courte": (_with(bars=[["2026-11-20", 228.1, 231.45]]), "bars"),
    "date invalide": (_with_bar(0, 0, "2026-02-30"), "bars"),
    "columns différentes": (_with(columns=["date", "close"]), "columns"),
    "columns dans le désordre": (
        _with(columns=["date", "open", "high", "low", "adj_close", "close", "volume"]),
        "columns",
    ),
    "currency EUR": (_with(currency="EUR"), "currency"),
    "source inconnue": (_with(source="stooq"), "source"),
    "schema_version 2": (_with(schema_version=2), "schema_version"),
    "symbole invalide": (_with(symbol="aapl"), "symbol"),
    "last_updated sans fuseau": (_with(last_updated="2026-11-23T22:41:05"), "last_updated"),
    "last_updated hors UTC": (_with(last_updated="2026-11-23T22:41:05+01:00"), "last_updated"),
    "clé inconnue": (_with(extra_field=1), "extra_field"),
    "schema_version absent": (_without("schema_version"), "schema_version"),
    "columns absent": (_without("columns"), "columns"),
    "last_updated absent": (_without("last_updated"), "last_updated"),
}


@pytest.mark.parametrize(
    ("data", "expected"),
    list(INVALID_CASES.values()),
    ids=list(INVALID_CASES),
)
def test_prices_model_rejects_rule_violations(data: dict[str, Any], expected: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        PricesFile.model_validate(data)

    assert expected in str(excinfo.value)


def test_prices_model_is_immutable() -> None:
    prices = PricesFile.model_validate(_valid_prices())

    with pytest.raises(ValidationError):
        prices.symbol = "MSFT"  # type: ignore[misc]


# --- Exemples du contrat (le document et les modèles ne doivent pas diverger) -------------------


def _contract_example(section: str, index: int = 0) -> Any:
    """Bloc ```json n° `index` de la section `## {section}.` de `03-data-contracts.md`."""
    text = CONTRACTS.read_text(encoding="utf-8")
    start = text.index(f"\n## {section}.")
    end = text.find("\n## ", start + 1)
    blocks = re.findall(r"```json\n(.*?)\n```", text[start : end if end != -1 else None], re.S)
    assert len(blocks) > index, f"pas de bloc JSON n°{index} dans la section {section}"
    return json.loads(blocks[index])


def test_contract_example_prices_is_valid() -> None:
    PricesFile.model_validate(_contract_example("2"))


def test_contract_validate_example_is_valid() -> None:
    """F02 R8 : l'exemple de section `validate` du contrat §6 est accepté par `RunReport`."""
    report = RunReport.model_validate(_contract_example("6", index=1))

    (run,) = report.validate_
    assert run.exit_code == 1
    assert {v.rule for v in run.violations} == {"ohlc_inconsistent"}
    assert {w.rule for w in run.warnings} == {"missing_session", "large_move", "stale"}


def test_contract_example_run_report_is_valid() -> None:
    report = RunReport.model_validate(_contract_example("6"))

    assert report.session_date.isoformat() == "2026-11-23"
    assert [t.status for t in report.ingest[0].tickers] == ["ok", "failed"]


# --- Rapport de run (contrat §6) ----------------------------------------------------------------


def _ticker(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "symbol": "AAPL",
        "status": "ok",
        "mode": "incremental",
        "bars_added": 1,
        "bars_revised": 0,
        "history_rewritten": False,
        "rewrite_reason": None,
        "attempts": 1,
        "error": None,
    }
    data.update(changes)
    return data


def _report(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": 1,
        "session_date": "2026-11-23",
        "ingest": [
            {
                "started_at": "2026-11-23T22:31:02Z",
                "finished_at": "2026-11-23T22:32:10Z",
                "duration_s": 68.0,
                "args": {"symbols": None, "full": False, "start": None},
                "exit_code": 0,
                "tickers": [_ticker()],
                "warnings": [{"symbol": "NVDA", "date": "2026-11-22", "rule": "non_session_date"}],
            }
        ],
    }
    data.update(changes)
    return data


def test_run_report_roundtrip() -> None:
    report = RunReport.model_validate(_report())
    dumped = report.model_dump(mode="json")

    assert RunReport.model_validate(dumped) == report
    assert dumped["ingest"][0]["started_at"] == "2026-11-23T22:31:02Z"
    assert dumped["session_date"] == "2026-11-23"


def test_run_report_without_ingest_section() -> None:
    report = RunReport.model_validate({"schema_version": 1, "session_date": "2026-11-23"})

    assert report.ingest == []


def test_run_report_preserves_unknown_sections() -> None:
    signal_section = {"errors": [], "warnings": [{"symbol": "AAPL", "rule": "stale"}]}
    report = RunReport.model_validate(_report(signal=signal_section))

    assert report.model_dump(mode="json")["signal"] == signal_section


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "skipped"),
        ("mode", "partial"),
        ("rewrite_reason", "manual"),
        ("bars_added", -1),
        ("attempts", -1),
        ("symbol", "aapl"),
    ],
)
def test_ingest_ticker_result_enums(field: str, value: Any) -> None:
    with pytest.raises(ValidationError) as excinfo:
        IngestTickerResult.model_validate(_ticker(**{field: value}))

    assert field in str(excinfo.value)


def test_warning_rule_enum() -> None:
    with pytest.raises(ValidationError):
        IngestWarning.model_validate({"symbol": "AAPL", "date": None, "rule": "unknown_rule"})


def test_unchanged_ticker_has_no_mode() -> None:
    result = IngestTickerResult.model_validate(_ticker(status="unchanged", mode=None, bars_added=0))

    assert result.mode is None


INCONSISTENT_TICKERS: dict[str, dict[str, Any]] = {
    "réécrit sans raison": _ticker(history_rewritten=True, rewrite_reason=None),
    "raison sans réécriture": _ticker(history_rewritten=False, rewrite_reason="revision"),
    "échec sans erreur": _ticker(status="failed", error=None),
    "succès avec erreur": _ticker(status="ok", error="boom"),
}


@pytest.mark.parametrize(
    "data", list(INCONSISTENT_TICKERS.values()), ids=list(INCONSISTENT_TICKERS)
)
def test_ingest_ticker_result_consistency(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        IngestTickerResult.model_validate(data)


def _run_with(**changes: Any) -> dict[str, Any]:
    data = _report()
    data["ingest"][0].update(changes)
    return data


INVALID_RUNS: dict[str, dict[str, Any]] = {
    "fin avant début": _run_with(finished_at="2026-11-23T22:30:00Z"),
    "horodatage hors UTC": _run_with(started_at="2026-11-23T23:31:02+01:00"),
    "code de sortie 2": _run_with(exit_code=2),
    "durée négative": _run_with(duration_s=-1.0),
    "clé inconnue dans une exécution": _run_with(extra=1),
}


@pytest.mark.parametrize("data", list(INVALID_RUNS.values()), ids=list(INVALID_RUNS))
def test_ingest_run_rejects_invalid(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RunReport.model_validate(data)


# --- Section `validate` du rapport de run (F02 — R8) -------------------------------------------


def _validate_run(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "started_at": "2026-11-23T22:33:00Z",
        "finished_at": "2026-11-23T22:33:01Z",
        "duration_s": 1.2,
        "args": {"symbols": None, "all_history": False},
        "exit_code": 1,
        "files_checked": 3,
        "violations": [
            {
                "symbol": "AAPL",
                "date": "2026-11-20",
                "rule": "ohlc_inconsistent",
                "detail": "high 227.0 < max(open, close) 230.95",
            },
            {"symbol": "readme", "date": None, "rule": "unreadable", "detail": "JSON invalide"},
        ],
        "warnings": [
            {
                "symbol": "MSFT",
                "rule": "missing_session",
                "start": "2026-11-17",
                "end": "2026-11-18",
                "value": 2,
            },
            {
                "symbol": "NVDA",
                "rule": "large_move",
                "start": "2026-11-23",
                "end": "2026-11-23",
                "value": 0.6,
            },
            {"symbol": "SPY", "rule": "zero_volume", "start": "2026-11-23", "end": "2026-11-23"},
            {"symbol": "TSLA", "rule": "stale", "start": None, "end": None, "value": 5},
            {"symbol": "META", "rule": "missing_file", "start": None, "end": None},
        ],
    }
    data.update(changes)
    return data


def _warning(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "symbol": "AAPL",
        "rule": "large_move",
        "start": "2026-11-23",
        "end": "2026-11-23",
        "value": 0.6,
    }
    data.update(changes)
    return data


def test_validate_run_accepts_valid_entry() -> None:
    run = ValidateRun.model_validate(_validate_run())

    assert run.exit_code == 1
    assert [v.rule for v in run.violations] == ["ohlc_inconsistent", "unreadable"]
    assert run.violations[1].symbol == "readme"  # nom de fichier quelconque (orphelin)
    assert run.warnings[3].start is None
    assert ValidateRun.model_validate(run.model_dump(mode="json")) == run


def test_validate_run_without_violation_exits_0() -> None:
    run = ValidateRun.model_validate(_validate_run(exit_code=0, violations=[]))

    assert run.exit_code == 0


INVALID_VALIDATE_RUNS: dict[str, dict[str, Any]] = {
    "code 1 sans violation": _validate_run(violations=[]),
    "code 0 avec violation": _validate_run(exit_code=0),
    "code de sortie 2": _validate_run(exit_code=2),
    "fin avant début": _validate_run(finished_at="2026-11-23T22:32:00Z"),
    "horodatage hors UTC": _validate_run(started_at="2026-11-23T23:33:00+01:00"),
    "fichiers vérifiés négatif": _validate_run(files_checked=-1),
    "règle bloquante inconnue": _validate_run(
        violations=[{"symbol": "AAPL", "date": None, "rule": "bad_rule", "detail": "x"}]
    ),
    "règle d'avertissement inconnue": _validate_run(warnings=[_warning(rule="bad_rule")]),
    "début après fin": _validate_run(warnings=[_warning(start="2026-11-24")]),
    "large_move sans dates": _validate_run(warnings=[_warning(start=None, end=None)]),
    "large_move sans fin": _validate_run(warnings=[_warning(end=None)]),
    "stale avec dates": _validate_run(warnings=[_warning(rule="stale")]),
    "missing_file avec dates": _validate_run(warnings=[_warning(rule="missing_file")]),
    "symbole d'avertissement invalide": _validate_run(warnings=[_warning(symbol="aapl")]),
    "clé inconnue": _validate_run(extra=1),
    "argument inconnu": _validate_run(args={"symbols": None, "all_history": False, "full": True}),
}


@pytest.mark.parametrize(
    "data", list(INVALID_VALIDATE_RUNS.values()), ids=list(INVALID_VALIDATE_RUNS)
)
def test_validate_run_rules(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ValidateRun.model_validate(data)


def test_validate_violation_symbol_is_free_text() -> None:
    violation = ValidateViolation.model_validate(
        {"symbol": "readme", "date": None, "rule": "schema", "detail": "bars: champ requis"}
    )

    assert violation.symbol == "readme"


def test_validate_warning_value_is_optional() -> None:
    warning = ValidateWarning.model_validate(
        {"symbol": "SPY", "rule": "zero_volume", "start": "2026-11-23", "end": "2026-11-23"}
    )

    assert warning.value is None


def test_run_report_validate_alias_roundtrip() -> None:
    report = RunReport.model_validate(_report(validate=[_validate_run()]))

    assert report.validate_[0].files_checked == 3
    dumped = report.model_dump(mode="json", by_alias=True)
    assert "validate_" not in dumped
    assert dumped["validate"][0]["exit_code"] == 1
    assert RunReport.model_validate(dumped) == report
    assert "validate_" not in report.model_dump_json(by_alias=True)


def test_run_report_validate_section_is_typed() -> None:
    with pytest.raises(ValidationError):
        RunReport.model_validate(_report(validate=[_validate_run(exit_code=2)]))


def test_existing_ingest_only_report_still_valid() -> None:
    report = RunReport.model_validate(_report())

    assert report.validate_ == []


def test_run_report_dump_exclude_unset_omits_validate() -> None:
    dumped = RunReport.model_validate(_report()).model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )

    assert "validate" not in dumped
    assert dumped == _report()


def test_run_report_defines_validate_without_shadow_warning() -> None:
    """Le champ Python `validate_` (alias JSON `validate`) ne masque pas `BaseModel.validate`."""
    # Sous-processus : recharger le module ici changerait l'identité des classes des autres tests.
    result = subprocess.run(
        [sys.executable, "-W", "error", "-c", "import tradinghelper.schemas"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_run_report_schema_has_optional_validate_section() -> None:
    schema = json.loads(render_json_schemas()["run_report.schema.json"])

    assert "validate" in schema["properties"]
    assert "validate_" not in schema["properties"]
    assert "validate" not in schema.get("required", [])


def test_run_report_requires_schema_version_and_session_date() -> None:
    with pytest.raises(ValidationError) as excinfo:
        RunReport.model_validate({"ingest": []})

    assert "schema_version" in str(excinfo.value)
    assert "session_date" in str(excinfo.value)


# --- Génération des JSON Schemas (`th schemas`) -------------------------------------------------

EXPECTED_SCHEMA_FILES = ["prices.schema.json", "run_report.schema.json"]


def test_schema_models_registry() -> None:
    assert {"prices": PricesFile, "run_report": RunReport} == SCHEMA_MODELS


def test_render_json_schemas_format() -> None:
    rendered = render_json_schemas()

    assert sorted(rendered) == EXPECTED_SCHEMA_FILES
    for name, text in rendered.items():
        assert text.endswith("}\n"), name
        assert "\r" not in text, name
        schema = json.loads(text)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert text == json.dumps(schema, indent=2, ensure_ascii=False) + "\n", name


def test_prices_schema_requires_every_contract_key() -> None:
    schema = json.loads(render_json_schemas()["prices.schema.json"])

    assert set(schema["required"]) == {
        "schema_version",
        "symbol",
        "currency",
        "source",
        "columns",
        "last_updated",
        "bars",
    }
    assert schema["additionalProperties"] is False


def test_run_report_schema_allows_other_sections() -> None:
    schema = json.loads(render_json_schemas()["run_report.schema.json"])

    assert schema.get("additionalProperties", True) is not False
    assert set(schema["required"]) == {"schema_version", "session_date"}


def test_write_json_schemas_creates_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"

    written = write_json_schemas(out_dir)

    assert sorted(p.name for p in written) == EXPECTED_SCHEMA_FILES
    rendered = render_json_schemas()
    for path in written:
        assert path.read_bytes() == rendered[path.name].encode("utf-8")


def test_generated_schemas_match_committed() -> None:
    """Les fichiers de `schemas/` sont à jour : sinon lancer `uv run th schemas`."""
    for name, text in render_json_schemas().items():
        committed = REPO_ROOT / "schemas" / name
        assert committed.is_file(), f"{name} absent : lancer `uv run th schemas`"
        assert committed.read_bytes() == text.encode("utf-8"), f"{name} désynchronisé"


def test_schemas_command_works_without_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TH_CONFIG_DIR", str(tmp_path / "missing"))
    out_dir = tmp_path / "schemas"

    result = CliRunner().invoke(app, ["schemas", "--out-dir", str(out_dir)])

    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in out_dir.iterdir()) == EXPECTED_SCHEMA_FILES
    assert "prices.schema.json" in result.stdout


# --- Signaux — contrat §4 (F08 T5 ; réutilisés par F07) ------------------------------------------


def _valid_signals() -> dict[str, Any]:
    data: dict[str, Any] = _contract_example("4")
    return data


def _signals_with(**changes: Any) -> dict[str, Any]:
    data = _valid_signals()
    data["signals"][0].update(copy.deepcopy(changes))
    return data


def test_signals_file_contract_example_valid() -> None:
    signals = SignalsFile.model_validate(_valid_signals())

    (signal,) = signals.signals
    assert signal.action == "BUY"
    assert signal.explanation is not None
    assert signal.explanation[0].feature == "rsi_14"


def test_signals_file_explanation_is_optional() -> None:
    data = _valid_signals()
    del data["signals"][0]["explanation"]

    (signal,) = SignalsFile.model_validate(data).signals

    assert signal.explanation is None


def test_signals_file_accepts_hold_and_sell() -> None:
    for action in ("HOLD", "SELL"):
        (signal,) = SignalsFile.model_validate(_signals_with(action=action)).signals
        assert signal.action == action


def _signals_top_level(**changes: Any) -> dict[str, Any]:
    data = _valid_signals()
    data.update(changes)
    return data


INVALID_SIGNALS: dict[str, dict[str, Any]] = {
    "action_inconnue": _signals_with(action="STRONG_BUY"),
    "confidence_sup_1": _signals_with(confidence=1.01),
    "confidence_negative": _signals_with(confidence=-0.01),
    "confidence_nan": _signals_with(confidence=float("nan")),
    "target_weight_negatif": _signals_with(target_weight=-0.1),
    "target_weight_sup_1": _signals_with(target_weight=1.5),
    "horizon_nul": _signals_with(horizon_days=0),
    "symbole_invalide": _signals_with(symbol="aapl"),
    "cle_inconnue_signal": _signals_with(model="x"),
    "explication_6_entrees": _signals_with(
        explanation=[{"feature": f"f{i}", "contribution": 0.1} for i in range(6)]
    ),
    "cle_inconnue_fichier": _signals_top_level(extra=1),
    "schema_version_2": _signals_top_level(schema_version=2),
    "generated_at_non_utc": _signals_top_level(generated_at="2026-11-23T22:45:00+01:00"),
}


@pytest.mark.parametrize("data", list(INVALID_SIGNALS.values()), ids=list(INVALID_SIGNALS))
def test_signals_file_rules(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SignalsFile.model_validate(data)


# --- Export dashboard : fiche ticker et accueil — contrat §7 (F08 T6) ----------------------------

EXPORT_MANIFEST, EXPORT_TICKER, EXPORT_OVERVIEW, EXPORT_HEALTH = range(4)  # blocs JSON du §7


def _ticker_example() -> dict[str, Any]:
    data: dict[str, Any] = _contract_example("7", EXPORT_TICKER)
    return data


def _overview_example() -> dict[str, Any]:
    data: dict[str, Any] = _contract_example("7", EXPORT_OVERVIEW)
    return data


def test_ticker_file_contract_example_valid() -> None:
    ticker = TickerFile.model_validate(_ticker_example())

    assert ticker.series.close == [230.95, 232.4]
    assert ticker.markers[0].action == "BUY"


def test_ticker_series_columns_match_contract() -> None:
    """R6 : colonnes exportées, sans `adj_close` ni milieu de Bollinger."""
    assert list(TickerSeries.model_fields) == [
        "date", "open", "high", "low", "close", "volume",
        "sma20", "sma50", "sma200", "bb_upper", "bb_lower", "rsi14",
    ]  # fmt: skip


def test_ticker_series_accepts_null_warmup() -> None:
    data = _ticker_example()
    data["series"]["sma200"] = [None, None]

    assert TickerFile.model_validate(data).series.sma200 == [None, None]


def test_ticker_series_lengths_must_match() -> None:
    data = _ticker_example()
    data["series"]["rsi14"] = [61.42]

    with pytest.raises(ValidationError, match="longueur"):
        TickerFile.model_validate(data)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("close", float("nan")),
        ("open", float("inf")),
        ("sma20", float("nan")),
        ("rsi14", float("-inf")),
    ],
)
def test_export_floats_reject_nan(column: str, value: float) -> None:
    """R8, R14 : jamais de NaN ni d'infini dans un fichier d'export."""
    data = _ticker_example()
    data["series"][column][0] = value

    with pytest.raises(ValidationError):
        TickerFile.model_validate(data)


def test_overview_change_1d_rejects_nan() -> None:
    data = _overview_example()
    data["tickers"][0]["change_1d"] = float("nan")

    with pytest.raises(ValidationError):
        OverviewFile.model_validate(data)


def test_marker_action_buy_or_sell_only() -> None:
    """R9 : HOLD n'est jamais un marqueur."""
    data = _ticker_example()
    data["markers"][0]["action"] = "HOLD"

    with pytest.raises(ValidationError):
        TickerFile.model_validate(data)


def test_ticker_volume_is_non_negative_int() -> None:
    data = _ticker_example()
    data["series"]["volume"][0] = -1

    with pytest.raises(ValidationError):
        TickerFile.model_validate(data)


def test_overview_contract_example_valid() -> None:
    overview = OverviewFile.model_validate(_overview_example())

    assert overview.tickers[0].spark[-1] == 232.4
    assert overview.leaderboard == []
    assert overview.latest_signals == []
    assert overview.kpis.best_strategy_30d is None


def test_overview_spark_max_60() -> None:
    data = _overview_example()
    data["tickers"][0]["spark"] = [100.0] * (SPARK_LENGTH + 1)

    with pytest.raises(ValidationError):
        OverviewFile.model_validate(data)


def test_overview_m3_rows_typed() -> None:
    """Sections M3 vides en M1 mais typées (R16) : une ligne de leaderboard et un signal enrichi."""
    data = _overview_example()
    data["leaderboard"] = [
        {"strategy_id": "buy_hold", "kind": "baseline", "equity": 10234.56, "return_30d": 0.0123,
         "sharpe_oos": 0.9, "random_percentile": 0.55}
    ]  # fmt: skip
    signal = dict(
        _valid_signals()["signals"][0], model_id="lgbm_dir5_20261122_ab12cd", sharpe_oos=1.1
    )
    data["latest_signals"] = [signal]

    overview = OverviewFile.model_validate(data)

    assert overview.leaderboard[0].kind == "baseline"
    assert overview.latest_signals[0].model_id == "lgbm_dir5_20261122_ab12cd"


def test_export_signal_extends_signal() -> None:
    """P8 : un signal exporté est un signal du §4 plus le modèle et sa performance."""
    assert issubclass(ExportSignal, Signal)
    assert {"model_id", "sharpe_oos"} <= set(ExportSignal.model_fields)
    with pytest.raises(ValidationError):  # champs P8 obligatoires (nuls autorisés)
        ExportSignal.model_validate(_valid_signals()["signals"][0])
