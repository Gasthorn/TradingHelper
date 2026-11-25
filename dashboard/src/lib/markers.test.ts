import { describe, expect, it } from "vitest";

import type { ManifestStrategy } from "../types/export_manifest";
import type { ExportMarker } from "../types/export_ticker";
import { strategyOptions, visibleMarkers } from "./markers";

const MARKERS: ExportMarker[] = [
  { date: "2026-11-20", strategy_id: "lgbm_dir5_v3", action: "BUY", confidence: 0.67 },
  { date: "2026-11-20", strategy_id: "sma_cross", action: "SELL", confidence: 0.55 },
  { date: "2026-11-23", strategy_id: "lgbm_dir5_v3", action: "SELL", confidence: 0.38 },
  { date: "2026-11-24", strategy_id: "lgbm_dir5_v3", action: "BUY", confidence: 0.6 },
];

const STRATEGIES: ManifestStrategy[] = [
  { id: "lgbm_dir5_v3", kind: "model", model_id: "lgbm_dir5_20261122_ab12cd", sharpe_oos: 1.1 },
  { id: "buy_hold", kind: "baseline", model_id: null, sharpe_oos: 0.8 },
];

const DATES: ReadonlySet<string> = new Set(["2026-11-19", "2026-11-20", "2026-11-23"]);

describe("strategyOptions (R17)", () => {
  it("liste les stratégies présentes, uniques et triées", () => {
    expect(strategyOptions(MARKERS)).toEqual(["lgbm_dir5_v3", "sma_cross"]);
  });

  it("est vide sans marqueur (sélecteur masqué, R4)", () => {
    expect(strategyOptions([])).toEqual([]);
  });
});

describe("visibleMarkers (R17, P8)", () => {
  it("sans filtre, garde tous les marqueurs dont la date est dans la série, dans l'ordre", () => {
    const views = visibleMarkers(MARKERS, null, DATES, STRATEGIES);
    expect(views.map((m) => [m.date, m.strategy_id, m.action])).toEqual([
      ["2026-11-20", "lgbm_dir5_v3", "BUY"],
      ["2026-11-20", "sma_cross", "SELL"],
      ["2026-11-23", "lgbm_dir5_v3", "SELL"],
    ]);
  });

  it("filtre par stratégie", () => {
    const views = visibleMarkers(MARKERS, "lgbm_dir5_v3", DATES, STRATEGIES);
    expect(views.map((m) => m.date)).toEqual(["2026-11-20", "2026-11-23"]);
    expect(views.every((m) => m.strategy_id === "lgbm_dir5_v3")).toBe(true);
  });

  it("ignore sans erreur un marqueur dont la date est absente de la série", () => {
    const views = visibleMarkers(MARKERS, null, DATES, STRATEGIES);
    expect(views.some((m) => m.date === "2026-11-24")).toBe(false);
  });

  it("ajoute le modèle et sa performance depuis manifest.strategies (P8)", () => {
    const [first] = visibleMarkers(MARKERS, "lgbm_dir5_v3", DATES, STRATEGIES);
    expect(first).toEqual({
      date: "2026-11-20",
      strategy_id: "lgbm_dir5_v3",
      action: "BUY",
      confidence: 0.67,
      modelId: "lgbm_dir5_20261122_ab12cd",
      sharpeOos: 1.1,
      known: true,
    });
  });

  it("signale une stratégie absente du manifest, valeurs à null", () => {
    const [view] = visibleMarkers(MARKERS, "sma_cross", DATES, STRATEGIES);
    expect(view).toMatchObject({ strategy_id: "sma_cross", modelId: null, sharpeOos: null, known: false });
  });

  it("renvoie une liste vide pour une stratégie sans marqueur", () => {
    expect(visibleMarkers(MARKERS, "buy_hold", DATES, STRATEGIES)).toEqual([]);
  });

  it("ne modifie pas les marqueurs d'entrée", () => {
    const copy = structuredClone(MARKERS);
    visibleMarkers(MARKERS, null, DATES, STRATEGIES);
    expect(MARKERS).toEqual(copy);
  });
});
