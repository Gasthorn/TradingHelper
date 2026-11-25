// Mesure Lighthouse de l'Overview (spec F09 — R26) : `npm run lighthouse`, à la vérification
// (pas en CI, décision Q6). Build `dist-lh/` sans public/, fixture `m1` copiée dans `data/`,
// `vite preview`, 3 mesures avec la configuration mobile par défaut de Lighthouse, dans le
// Chromium installé par Playwright (`npx playwright install chromium`). Code 1 si la médiane du
// score de performance est < 90 ou si plus de 5 Mo sont transférés.
import { cpSync, rmSync } from "node:fs";
import process from "node:process";
import { URL, fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";
import lighthouse from "lighthouse";
import { build, preview } from "vite";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const OUT_DIR = "dist-lh";
const PORT = 4175;
const DEBUG_PORT = 9223;
const RUNS = 3;
const MIN_SCORE = 90;
const MAX_BYTES = 5 * 1024 * 1024;

const median = (values) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];

process.chdir(ROOT);
delete process.env.TH_DASHBOARD_BASE;
rmSync(OUT_DIR, { recursive: true, force: true });
await build({ logLevel: "warn", publicDir: false, build: { outDir: OUT_DIR, emptyOutDir: true } });
cpSync("tests/fixtures/m1", `${OUT_DIR}/data`, { recursive: true });

const server = await preview({ logLevel: "warn", build: { outDir: OUT_DIR }, preview: { port: PORT, strictPort: true } });
const browser = await chromium.launch({ args: [`--remote-debugging-port=${DEBUG_PORT}`] });
const url = `http://localhost:${PORT}/`;

const runs = [];
try {
  for (let i = 1; i <= RUNS; i++) {
    const result = await lighthouse(url, { port: DEBUG_PORT, output: "json", logLevel: "error", onlyCategories: ["performance"] });
    if (result === undefined) throw new Error("Lighthouse n'a renvoyé aucun résultat");
    const { lhr } = result;
    // Garde-fou : la mesure doit porter sur l'Overview remplie, pas sur une page d'erreur.
    const requests = lhr.audits["network-requests"]?.details?.items ?? [];
    if (!requests.some((item) => String(item.url).includes("/data/overview.json") && item.statusCode === 200)) {
      throw new Error("overview.json n'a pas été chargé : la mesure ne porte pas sur l'Overview");
    }
    const run = {
      score: Math.round((lhr.categories.performance.score ?? 0) * 100),
      lcp: lhr.audits["largest-contentful-paint"]?.numericValue ?? NaN,
      fcp: lhr.audits["first-contentful-paint"]?.numericValue ?? NaN,
      tbt: lhr.audits["total-blocking-time"]?.numericValue ?? NaN,
      cls: lhr.audits["cumulative-layout-shift"]?.numericValue ?? NaN,
      bytes: lhr.audits["total-byte-weight"]?.numericValue ?? NaN,
    };
    runs.push(run);
    process.stdout.write(
      `mesure ${i} : score ${run.score}, LCP ${(run.lcp / 1000).toFixed(2)} s, FCP ${(run.fcp / 1000).toFixed(2)} s, ` +
        `TBT ${Math.round(run.tbt)} ms, CLS ${run.cls.toFixed(3)}, ${(run.bytes / 1024).toFixed(1)} Ko transférés\n`,
    );
  }
} finally {
  await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
}

const score = median(runs.map((r) => r.score));
const bytes = Math.max(...runs.map((r) => r.bytes));
const ok = score >= MIN_SCORE && bytes < MAX_BYTES;
process.stdout.write(
  `lighthouse : médiane ${score} (seuil ${MIN_SCORE}), ${(bytes / 1024).toFixed(1)} Ko transférés au plus (seuil 5 Mo) — ${ok ? "OK" : "ÉCHEC"}\n`,
);
process.exitCode = ok ? 0 : 1;
