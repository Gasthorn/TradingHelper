import preact from "@preact/preset-vite";
import { defineConfig, loadEnv } from "vite";

/**
 * `base` configurable (spec F00 — R14) via TH_DASHBOARD_BASE :
 * "/" en local, "/TradingHelper/" pour https://<user>.github.io/TradingHelper/ (F09 R7).
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

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "TH_");
  return {
    base: resolveBase(env.TH_DASHBOARD_BASE),
    plugins: [preact()],
  };
});
