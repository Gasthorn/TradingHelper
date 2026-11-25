import { describe, expect, it } from "vitest";

import { parseHash, tickerHash } from "./routes";

describe("tickerHash", () => {
  it.each(["AAPL", "BRK.B", "BRK-B"])("fait l'aller-retour avec parseHash pour %s", (symbol) => {
    expect(parseHash(tickerHash(symbol))).toEqual({ page: "ticker", symbol });
  });
});

describe("parseHash — Overview (R1)", () => {
  it.each(["", "#", "#/", "#//"])("%j → overview", (hash) => {
    expect(parseHash(hash)).toEqual({ page: "overview" });
  });
});

describe("parseHash — Ticker (R1, R14)", () => {
  it("lit le symbole", () => {
    expect(parseHash("#/ticker/AAPL")).toEqual({ page: "ticker", symbol: "AAPL" });
  });

  it("ignore la casse (majuscules)", () => {
    expect(parseHash("#/ticker/brk.b")).toEqual({ page: "ticker", symbol: "BRK.B" });
  });

  it("décode un symbole encodé", () => {
    expect(parseHash("#/ticker/BRK%2DB")).toEqual({ page: "ticker", symbol: "BRK-B" });
    expect(parseHash("#/ticker/brk%2db")).toEqual({ page: "ticker", symbol: "BRK-B" });
  });

  it("tolère une barre finale", () => {
    expect(parseHash("#/ticker/AAPL/")).toEqual({ page: "ticker", symbol: "AAPL" });
  });

  it("refuse un encodage invalide sans lever d'exception", () => {
    expect(parseHash("#/ticker/%E0%A4%A")).toEqual({ page: "not_found" });
  });

  it("refuse un symbole vide ou un segment de trop", () => {
    expect(parseHash("#/ticker/")).toEqual({ page: "not_found" });
    expect(parseHash("#/ticker")).toEqual({ page: "not_found" });
    expect(parseHash("#/ticker/%20")).toEqual({ page: "not_found" });
    expect(parseHash("#/ticker/AAPL/extra")).toEqual({ page: "not_found" });
  });
});

describe("parseHash — routes inconnues ou non livrées en M1 (R1)", () => {
  it.each(["#/inconnu", "#/portfolios", "#/portfolio/buy_hold", "#/models", "#/health", "#ticker/AAPL", "#/TICKER/AAPL"])(
    "%j → not_found",
    (hash) => {
      expect(parseHash(hash)).toEqual({ page: "not_found" });
    },
  );
});
