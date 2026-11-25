/** Utilisable à 375 × 812 (spec F09 — R9). Projet Playwright « mobile ». */
import { type Locator, type Page } from "@playwright/test";

import { expect, failFile, gotoRoute, test, useFixture } from "./support";

/** Attend que la page soit rendue (titre de niveau 1 ou message d'erreur). */
async function ready(page: Page): Promise<void> {
  await expect(page.locator("h1, [role=alert]").first()).toBeVisible();
}

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

for (const hash of ["#/", "#/ticker/AAPL", "#/ticker/BRK.B", "#/inconnu", "#/ticker/ZZZ"]) {
  test(`${hash} : aucun défilement horizontal de la page à 375 px`, async ({ page }) => {
    await useFixture(page, "m1");
    await gotoRoute(page, hash);
    await ready(page);
    if (hash.startsWith("#/ticker/") && hash !== "#/ticker/ZZZ") {
      await expect(page.getByTestId("price-chart")).toHaveAttribute("data-bars", /\d+/);
    }

    expect(await page.evaluate(() => window.innerWidth)).toBe(375);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  });
}

test("page d'erreur : aucun défilement horizontal", async ({ page, consoleErrors }) => {
  consoleErrors.allow(/404/);
  await useFixture(page, "m1");
  await failFile(page, "overview.json", "missing");
  await gotoRoute(page);
  await expect(page.getByRole("alert")).toBeVisible();

  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
});

test("le tableau des cours défile dans son conteneur, pas la page", async ({ page }) => {
  await useFixture(page, "m1");
  await gotoRoute(page);
  const region = page.getByRole("region", { name: "Tableau des cours" });
  await expect(region).toBeVisible();

  const box = await region.boundingBox();
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(375);
});

async function expectTouchTarget(target: Locator): Promise<void> {
  const box = await target.boundingBox();
  expect(box, "cible visible").not.toBeNull();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
}

test("cibles tactiles d'au moins 44 × 44 px : en-tête, bascule de thème", async ({ page }) => {
  await useFixture(page, "m1");
  await gotoRoute(page);
  await ready(page);

  await expectTouchTarget(page.getByRole("banner").getByRole("link", { name: "TradingHelper" }));
  await expectTouchTarget(page.getByRole("button", { name: /Thème/ }));
});

test("cibles tactiles d'au moins 44 × 44 px : sélecteurs de la fiche", async ({ page }) => {
  await useFixture(page, "m1-signals");
  await gotoRoute(page, "#/ticker/AAPL");
  await ready(page);

  const periods = page.getByRole("radiogroup", { name: "Période" }).locator("label");
  for (let i = 0; i < (await periods.count()); i++) await expectTouchTarget(periods.nth(i));
  const overlays = page.getByRole("group", { name: "Indicateurs" }).locator("label");
  for (let i = 0; i < (await overlays.count()); i++) await expectTouchTarget(overlays.nth(i));
  await expectTouchTarget(page.getByRole("combobox", { name: "Stratégie" }));
});

test("page introuvable : lien de retour d'au moins 44 px de haut", async ({ page }) => {
  await useFixture(page, "m1");
  await gotoRoute(page, "#/inconnu");

  await expectTouchTarget(page.getByRole("link", { name: "Retour à l'accueil" }));
});
