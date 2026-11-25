/**
 * Tests e2e du dashboard (spec F09 — R25). Lancer avec `npm run test:e2e` depuis `dashboard/` :
 * le script construit `dist/` (base "/") et `dist-base/` (base "/TradingHelper/") puis lance
 * Playwright. Les données sont servies par interception (`e2e/support.ts::useFixture`),
 * jamais par le réseau.
 */
import { defineConfig, devices } from "@playwright/test";

const ROOT = "http://localhost:4173/";
const BASE = "http://localhost:4174/TradingHelper/";

export default defineConfig({
  testDir: ".",
  outputDir: "../test-results",
  forbidOnly: true,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: ROOT,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], baseURL: ROOT },
      testIgnore: [/mobile\.spec\.ts$/, /base\.spec\.ts$/],
    },
    {
      name: "mobile",
      use: { ...devices["Desktop Chrome"], baseURL: ROOT, viewport: { width: 375, height: 812 }, hasTouch: true },
      testMatch: /mobile\.spec\.ts$/,
    },
    {
      name: "base",
      use: { ...devices["Desktop Chrome"], baseURL: BASE },
      testMatch: /base\.spec\.ts$/,
    },
  ],
  webServer: [
    {
      command: "npx vite preview --port 4173 --strictPort",
      cwd: "..",
      url: ROOT,
      reuseExistingServer: true,
    },
    {
      command: "npx vite preview --outDir dist-base --port 4174 --strictPort",
      cwd: "..",
      url: BASE,
      env: { TH_DASHBOARD_BASE: "/TradingHelper/" },
      reuseExistingServer: true,
    },
  ],
});
