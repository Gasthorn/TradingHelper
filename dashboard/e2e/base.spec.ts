/**
 * Déploiement sous GitHub Pages (spec F09 — R10) : build `dist-base/` (base "/TradingHelper/")
 * servi sous ce chemin par le projet Playwright « base ».
 */
import { type Page } from "@playwright/test";

import { DISCLAIMER, expect, gotoRoute, test, useFixture } from "./support";

const BASE_PATH = "/TradingHelper/";
const ORIGIN = "http://localhost:4174"; // serveur du projet « base » (e2e/playwright.config.ts)

/** Chemins des requêtes vers l'origine du site, document principal compris. */
function sameOriginRequests(page: Page): string[] {
  const paths: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === ORIGIN) paths.push(url.pathname);
  });
  return paths;
}

test.beforeEach(async ({ page }) => {
  await useFixture(page, "m1");
});

test("la page est servie sous /TradingHelper/", async ({ page }) => {
  await gotoRoute(page);
  expect(new URL(page.url()).pathname).toBe(BASE_PATH);
  await expect(page.getByRole("note")).toHaveText(DISCLAIMER);
});

test("l'Overview charge ses données sous la base", async ({ page }) => {
  const requested: string[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (pathname.includes("/data/")) requested.push(pathname);
  });
  await gotoRoute(page);

  await expect(page.getByRole("table", { name: /Cours/ }).locator("tbody tr")).toHaveCount(4);
  expect(requested.sort()).toEqual([`${BASE_PATH}data/manifest.json`, `${BASE_PATH}data/overview.json`]);
});

test("la fiche ticker et son graphique se chargent sous la base", async ({ page }) => {
  await gotoRoute(page, "#/ticker/AAPL");

  await expect(page.getByTestId("price-chart")).toHaveAttribute("data-bars", /\d+/);
});

test("aucune requête de même origine hors de /TradingHelper/", async ({ page }) => {
  const paths = sameOriginRequests(page);
  await gotoRoute(page);
  await expect(page.getByRole("table", { name: /Cours/ })).toBeVisible();
  await page.getByRole("link", { name: "AAPL", exact: true }).click();
  await expect(page.getByTestId("price-chart")).toHaveAttribute("data-bars", /\d+/);
  await page.getByRole("banner").getByRole("link", { name: "TradingHelper" }).click();
  await expect(page.getByRole("table", { name: /Cours/ })).toBeVisible();

  expect(paths.length).toBeGreaterThan(0);
  expect(paths.filter((p) => !p.startsWith(BASE_PATH))).toEqual([]);
  expect(new URL(page.url()).pathname).toBe(BASE_PATH);
});
