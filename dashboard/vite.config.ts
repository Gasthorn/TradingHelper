/// <reference types="vitest/config" />
import preact from "@preact/preset-vite";
import { defineConfig, loadEnv } from "vite";

/**
 * `base` configurable (spec F00 — R14) via TH_DASHBOARD_BASE :
 * "/" en local, "/TradingHelper/" pour https://<user>.github.io/TradingHelper/ (F09 R10).
 * `loadEnv` lit l'environnement du processus (et d'éventuels fichiers .env) sans exposer
 * ces variables au code client : seules celles préfixées par VITE_ le sont.
 */
function resolveBase(raw: string | undefined): string {
  const base = raw?.trim() || "/";
  if (!base.startsWith("/") || !base.endsWith("/")) {
    throw new Error(`TH_DASHBOARD_BASE doit commencer et finir par "/" (reçu : "${base}")`);
  }
  return base;
}

/**
 * Tests unitaires (spec F09 — R23) : chaque test tourne sous deux fuseaux extrêmes, pour
 * détecter toute conversion implicite d'une date de séance en instant (R11).
 */
const TEST_TIMEZONES = ["America/Los_Angeles", "Pacific/Auckland"] as const;

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "TH_");
  return {
    base: resolveBase(env.TH_DASHBOARD_BASE),
    plugins: [preact()],
    // Builds et résultats e2e (F09 R25) : ne pas recharger le serveur de dev à chaque `npm run test:e2e`.
    server: { watch: { ignored: ["**/dist-*/**", "**/test-results/**", "**/playwright-report/**"] } },
    test: {
      projects: TEST_TIMEZONES.map((tz) => ({
        extends: true,
        test: {
          name: tz,
          environment: "node",
          include: ["src/**/*.test.ts"],
          env: { TZ: tz },
        },
      })),
    },
  };
});
