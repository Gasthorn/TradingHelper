import { describe, expect, it } from "vitest";

import { MANIFEST_PATH, dataUrl } from "./urls";

describe("dataUrl (spec F09 — R2, R10)", () => {
  const entry = { path: "overview.json", sha256: "9f2c4e1a7b3d5c60" };

  it("préfixe le chemin par base + data/ et ajoute l'empreinte du manifest", () => {
    expect(dataUrl("/", entry)).toBe("/data/overview.json?v=9f2c4e1a7b3d5c60");
  });

  it("respecte la base de GitHub Pages", () => {
    expect(dataUrl("/TradingHelper/", entry)).toBe(
      "/TradingHelper/data/overview.json?v=9f2c4e1a7b3d5c60",
    );
  });

  it("conserve un chemin imbriqué", () => {
    expect(dataUrl("/TradingHelper/", { path: "tickers/AAPL.json", sha256: "1a2b3c4d5e6f7a8b" })).toBe(
      "/TradingHelper/data/tickers/AAPL.json?v=1a2b3c4d5e6f7a8b",
    );
  });

  // Le contrat (`ExportPath`) n'autorise que [A-Za-z0-9_.-] et "/" : aucun encodage requis.
  it("laisse intact un symbole à point", () => {
    expect(dataUrl("/", { path: "tickers/BRK.B.json", sha256: "0000000000000000" })).toBe(
      "/data/tickers/BRK.B.json?v=0000000000000000",
    );
  });
});

describe("MANIFEST_PATH", () => {
  it("désigne manifest.json à la racine des données", () => {
    expect(MANIFEST_PATH).toBe("manifest.json");
  });
});

describe("fuseau des tests (spec F09 — R11, plan T1)", () => {
  it("s'exécute dans le fuseau imposé par le projet Vitest", () => {
    const expected: unknown = import.meta.env.TZ;
    expect(["America/Los_Angeles", "Pacific/Auckland"]).toContain(expected);
    expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe(expected);
  });
});
