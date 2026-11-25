// Builds des tests e2e (spec F09 — R25, R10) : `dist/` avec la base "/" et `dist-base/` avec
// la base de GitHub Pages "/TradingHelper/", servis par `vite preview` (e2e/playwright.config.ts).
// API JS de Vite plutôt que variables d'environnement dans package.json : portable sous Windows.
import process from "node:process";
import { build } from "vite";

delete process.env.TH_DASHBOARD_BASE;
await build({ logLevel: "warn" });

process.env.TH_DASHBOARD_BASE = "/TradingHelper/";
await build({ logLevel: "warn", build: { outDir: "dist-base", emptyOutDir: true } });
