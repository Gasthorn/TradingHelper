import { describe, expect, it } from "vitest";

import {
  EMPTY,
  changeParts,
  formatAmount,
  formatConfidence,
  formatDate,
  formatPercent,
  formatPrice,
} from "./format";

/** Séparateurs attendus, explicites pour ne pas dépendre de la version d'ICU (R11). */
const THIN = "\u202f"; // espace fine insécable : séparateur de milliers
const NBSP = "\u00a0"; // espace insécable : avant $ et %
const MINUS = "\u2212"; // signe moins typographique

describe("EMPTY", () => {
  it("est un tiret cadratin", () => {
    expect(EMPTY).toBe("—");
  });
});

describe("formatPrice (R11)", () => {
  it("affiche 2 décimales au-dessus de 1 $", () => {
    expect(formatPrice(232.4)).toBe(`232,40${NBSP}$`);
  });

  it("affiche 4 décimales sous 1 $ (cours anciens ajustés des splits)", () => {
    expect(formatPrice(0.1234)).toBe(`0,1234${NBSP}$`);
  });

  it("sépare les milliers par une espace fine insécable", () => {
    expect(formatPrice(1234.5)).toBe(`1${THIN}234,50${NBSP}$`);
  });

  it("bascule à 2 décimales dès 1 $ exactement", () => {
    expect(formatPrice(1)).toBe(`1,00${NBSP}$`);
  });

  it("affiche — pour null", () => {
    expect(formatPrice(null)).toBe(EMPTY);
  });
});

describe("formatAmount (R11)", () => {
  it("affiche un montant à 2 décimales avec séparateur de milliers et devise", () => {
    expect(formatAmount(1234.56)).toBe(`1${THIN}234,56${NBSP}$`);
  });

  it("affiche un montant négatif avec le signe moins typographique", () => {
    expect(formatAmount(-10012.4)).toBe(`${MINUS}10${THIN}012,40${NBSP}$`);
  });

  it("affiche — pour null", () => {
    expect(formatAmount(null)).toBe(EMPTY);
  });
});

describe("formatPercent (R11)", () => {
  it("affiche un ratio en pourcentage à 2 décimales, sans signe par défaut", () => {
    expect(formatPercent(0.0063)).toBe(`0,63${NBSP}%`);
    expect(formatPercent(-0.14)).toBe(`${MINUS}14,00${NBSP}%`);
  });

  it("signe les variations", () => {
    expect(formatPercent(0.0063, { signed: true })).toBe(`+0,63${NBSP}%`);
    expect(formatPercent(-0.012, { signed: true })).toBe(`${MINUS}1,20${NBSP}%`);
  });

  it("n'affiche aucun signe pour une valeur arrondie à zéro", () => {
    expect(formatPercent(0, { signed: true })).toBe(`0,00${NBSP}%`);
    expect(formatPercent(-0.00001, { signed: true })).toBe(`0,00${NBSP}%`);
    expect(formatPercent(-0.00001)).toBe(`0,00${NBSP}%`);
  });

  it("affiche — pour null", () => {
    expect(formatPercent(null)).toBe(EMPTY);
    expect(formatPercent(null, { signed: true })).toBe(EMPTY);
  });
});

describe("formatConfidence (R11)", () => {
  it("affiche la confiance en pourcentage entier", () => {
    expect(formatConfidence(0.67)).toBe(`67${NBSP}%`);
    expect(formatConfidence(0.384)).toBe(`38${NBSP}%`);
    expect(formatConfidence(1)).toBe(`100${NBSP}%`);
  });

  it("affiche — pour null", () => {
    expect(formatConfidence(null)).toBe(EMPTY);
  });
});

describe("formatDate (R11)", () => {
  it("affiche une date de séance en JJ/MM/AAAA sans conversion de fuseau", () => {
    expect(formatDate("2026-11-23")).toBe("23/11/2026");
    expect(formatDate("2010-01-04")).toBe("04/01/2010");
  });

  it("affiche — pour null", () => {
    expect(formatDate(null)).toBe(EMPTY);
  });
});

describe("valeurs non finies", () => {
  it("affiche — plutôt que NaN ou Infinity", () => {
    expect(formatPrice(Number.NaN)).toBe(EMPTY);
    expect(formatPercent(Number.POSITIVE_INFINITY)).toBe(EMPTY);
  });
});

describe("changeParts (R8 : jamais la couleur seule)", () => {
  it("donne flèche ▲, signe + et direction up pour une hausse", () => {
    expect(changeParts(0.0063)).toEqual({ direction: "up", arrow: "▲", text: `+0,63${NBSP}%` });
  });

  it("donne flèche ▼, signe − et direction down pour une baisse", () => {
    expect(changeParts(-0.012)).toEqual({ direction: "down", arrow: "▼", text: `${MINUS}1,20${NBSP}%` });
  });

  it("ne donne ni flèche ni signe pour une variation arrondie à zéro", () => {
    expect(changeParts(0.00001)).toEqual({ direction: "flat", arrow: "", text: `0,00${NBSP}%` });
  });

  it("donne — pour une variation indisponible (une seule barre)", () => {
    expect(changeParts(null)).toEqual({ direction: "none", arrow: "", text: EMPTY });
  });
});
