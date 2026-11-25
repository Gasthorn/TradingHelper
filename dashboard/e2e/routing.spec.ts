/** Routage par hash, liens profonds et page introuvable (spec F09 — R1). */
import { expect, gotoRoute, test, useFixture } from "./support";

test.beforeEach(async ({ page }) => {
  await useFixture(page, "m1");
});

test("un lien profond rechargé affiche la page demandée", async ({ page }) => {
  await gotoRoute(page, "#/ticker/AAPL");
  await expect(page.getByRole("heading", { level: 1, name: "AAPL" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "AAPL" })).toBeVisible();
});

test("la navigation par hash change de page sans rechargement", async ({ page }) => {
  await gotoRoute(page, "#/inconnu");
  await page.evaluate(() => {
    (window as unknown as { marker: number }).marker = 1;
  });

  await page.getByRole("link", { name: "Retour à l'accueil" }).click();
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "Page introuvable" })).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { marker?: number }).marker)).toBe(1);
});

for (const hash of ["#/inconnu", "#/portfolios", "#/models", "#/health", "#/portfolio/buy_hold", "#/ticker/"]) {
  test(`${hash} affiche « Page introuvable » avec un lien vers l'Overview`, async ({ page }) => {
    await gotoRoute(page, hash);

    await expect(page.getByRole("heading", { level: 1, name: "Page introuvable" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Retour à l'accueil" })).toHaveAttribute("href", "#/");
  });
}

test("l'en-tête porte le titre du site et un lien vers l'accueil", async ({ page }) => {
  await gotoRoute(page, "#/ticker/AAPL");

  const header = page.getByRole("banner");
  await expect(header.getByRole("link", { name: "TradingHelper" })).toHaveAttribute("href", "#/");
  await expect(page).toHaveTitle("TradingHelper");
});
