import { describe, expect, it } from "vitest";

import { isAllNull, linePoints, periodWindow } from "./series";

/** Séances du 2026-09-01 au 2026-11-23, du lundi au vendredi (jours fériés ignorés). */
function weekdaysUntil(first: string, last: string): string[] {
  const out: string[] = [];
  const end = Date.UTC(Number(last.slice(0, 4)), Number(last.slice(5, 7)) - 1, Number(last.slice(8, 10)));
  let t = Date.UTC(Number(first.slice(0, 4)), Number(first.slice(5, 7)) - 1, Number(first.slice(8, 10)));
  for (; t <= end; t += 86_400_000) {
    const day = new Date(t).getUTCDay();
    if (day !== 0 && day !== 6) out.push(new Date(t).toISOString().slice(0, 10));
  }
  return out;
}

const DATES = weekdaysUntil("2026-09-01", "2026-11-23");

describe("periodWindow (R16)", () => {
  it("1M commence à la première séance ≥ dernière date − 1 mois", () => {
    const w = periodWindow(DATES, "1M");
    expect(DATES[w.from]).toBe("2026-10-23");
    expect(DATES[w.from - 1]).toBe("2026-10-22");
    expect(w.to).toBe(DATES.length - 1);
  });

  it("prend la séance suivante quand la borne tombe un week-end", () => {
    const dates = weekdaysUntil("2026-09-01", "2026-11-25"); // borne 1M = dim. 2026-10-25
    expect(dates[periodWindow(dates, "1M").from]).toBe("2026-10-26");
  });

  it("renvoie toute la série quand l'historique est plus court que la période", () => {
    expect(periodWindow(DATES, "6M")).toEqual({ from: 0, to: DATES.length - 1 });
    expect(periodWindow(DATES, "5A")).toEqual({ from: 0, to: DATES.length - 1 });
  });

  it("Max renvoie toute la série", () => {
    expect(periodWindow(DATES, "Max")).toEqual({ from: 0, to: DATES.length - 1 });
  });

  it("gère une seule barre et une série vide", () => {
    expect(periodWindow(["2026-11-23"], "1M")).toEqual({ from: 0, to: 0 });
    expect(periodWindow([], "6M")).toEqual({ from: 0, to: -1 });
  });
});

describe("linePoints (R15)", () => {
  const dates = ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23"];
  const values = [null, null, 10.5, null, 11.25];

  it("exclut les valeurs null (warm-up), sans zéro ni interpolation", () => {
    expect(linePoints(dates, values, { from: 0, to: 4 })).toEqual([
      { time: "2026-11-19", value: 10.5 },
      { time: "2026-11-23", value: 11.25 },
    ]);
  });

  it("respecte la fenêtre", () => {
    expect(linePoints(dates, values, { from: 3, to: 4 })).toEqual([{ time: "2026-11-23", value: 11.25 }]);
    expect(linePoints(dates, values, { from: 0, to: 1 })).toEqual([]);
  });

  it("renvoie une liste vide pour une fenêtre vide", () => {
    expect(linePoints([], [], { from: 0, to: -1 })).toEqual([]);
  });
});

describe("isAllNull (R15)", () => {
  it("détecte une série entièrement nulle (sma200 sur un historique court)", () => {
    expect(isAllNull([null, null, null])).toBe(true);
    expect(isAllNull([])).toBe(true);
  });

  it("est faux dès qu'une valeur existe", () => {
    expect(isAllNull([null, 0, null])).toBe(false);
  });
});
