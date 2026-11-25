/** Thème clair / sombre / système (spec F09 — R7, décision Q9). */
import { type Page } from "@playwright/test";

import { expect, gotoRoute, test, useFixture } from "./support";

const toggle = (page: Page) => page.getByRole("button", { name: /Thème/ });
const theme = (page: Page) => page.evaluate(() => document.documentElement.dataset.theme);
const background = (page: Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await useFixture(page, "m1");
});

test("la bascule parcourt système → clair → sombre, sans rechargement", async ({ page }) => {
  await gotoRoute(page);
  await page.evaluate(() => {
    (window as unknown as { marker: number }).marker = 1;
  });
  await expect(toggle(page)).toHaveText(/Système/);
  const lightBackground = await background(page);

  await toggle(page).click();
  await expect(toggle(page)).toHaveText(/Clair/);
  expect(await theme(page)).toBe("light");

  await toggle(page).click();
  await expect(toggle(page)).toHaveText(/Sombre/);
  expect(await theme(page)).toBe("dark");
  expect(await background(page)).not.toBe(lightBackground);

  await toggle(page).click();
  await expect(toggle(page)).toHaveText(/Système/);
  expect(await theme(page)).toBe("light");
  expect(await page.evaluate(() => (window as unknown as { marker?: number }).marker)).toBe(1);
});

test("le choix survit à un rechargement", async ({ page }) => {
  await gotoRoute(page);
  await toggle(page).click();
  await toggle(page).click(); // sombre
  await page.reload();

  await expect(toggle(page)).toHaveText(/Sombre/);
  expect(await theme(page)).toBe("dark");
});

test("« système » suit prefers-color-scheme, y compris en direct", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await gotoRoute(page);
  expect(await theme(page)).toBe("dark");

  await page.emulateMedia({ colorScheme: "light" });
  await expect.poll(() => theme(page)).toBe("light");
});

test("le thème est posé avant le chargement de l'application (pas de flash)", async ({ page, consoleErrors }) => {
  consoleErrors.allow(/Failed to load resource|net::ERR_FAILED/);
  await page.addInitScript(() => {
    localStorage.setItem("th-theme", "dark");
  });
  await page.route("**/assets/*.js", (route) => route.abort());
  await gotoRoute(page);

  expect(await theme(page)).toBe("dark");
});

test("une valeur stockée invalide revient à « système »", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("th-theme", "fluo");
  });
  await page.emulateMedia({ colorScheme: "dark" });
  await gotoRoute(page);

  await expect(toggle(page)).toHaveText(/Système/);
  expect(await theme(page)).toBe("dark");
});

test("le graphique suit le thème sans rechargement ni recréation", async ({ page }) => {
  await gotoRoute(page, "#/ticker/AAPL");
  const chart = page.getByTestId("price-chart");
  await expect(chart).toHaveAttribute("data-theme", "light");
  const chartId = await chart.getAttribute("data-chart-id");
  /** Couleur du coin haut gauche du premier canvas (fond dessiné par le graphique). */
  const corner = () =>
    chart.locator("canvas").first().evaluate((canvas: HTMLCanvasElement) => {
      const context = canvas.getContext("2d");
      return context === null ? "" : Array.from(context.getImageData(2, 2, 1, 1).data).join(",");
    });
  await expect.poll(corner).not.toBe("");
  const lightCorner = await corner();

  await toggle(page).click(); // clair
  await toggle(page).click(); // sombre
  await expect(chart).toHaveAttribute("data-theme", "dark");
  await expect.poll(corner).not.toBe(lightCorner);
  expect(await chart.getAttribute("data-chart-id")).toBe(chartId);
  await expect(chart).toHaveAttribute("data-bars", /\d+/);
});
