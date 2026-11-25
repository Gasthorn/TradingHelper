/** Garde-fous de l'outillage e2e (spec F09 — R25) : fixtures servies, échecs simulés, console. */
import { failFile, gotoRoute, test, expect, useFixture } from "./support";

/** Statut et corps d'une requête de données faite depuis la page. */
async function fetchData(page: import("@playwright/test").Page, path: string) {
  return page.evaluate(async (p) => {
    const response = await fetch(`data/${p}?v=test`);
    return { status: response.status, body: await response.text() };
  }, path);
}

test("useFixture sert le manifest du jeu demandé", async ({ page }) => {
  await useFixture(page, "m1");
  await gotoRoute(page);

  const { status, body } = await fetchData(page, "manifest.json");
  expect(status).toBe(200);
  expect(JSON.parse(body)).toMatchObject({ schema_version: 1, data_as_of: "2026-11-23" });
});

test("useFixture sert un fichier imbriqué à point dans le nom", async ({ page }) => {
  await useFixture(page, "m1");
  await gotoRoute(page);

  const { status, body } = await fetchData(page, "tickers/BRK.B.json");
  expect(status).toBe(200);
  expect(JSON.parse(body)).toMatchObject({ symbol: "BRK.B" });
});

test("useFixture répond 404 pour un fichier absent du jeu", async ({ page, consoleErrors }) => {
  consoleErrors.allow(/404/);
  await useFixture(page, "empty");
  await gotoRoute(page);

  expect((await fetchData(page, "tickers/AAPL.json")).status).toBe(404);
});

test("failFile simule un fichier absent, illisible ou d'une autre version", async ({ page, consoleErrors }) => {
  consoleErrors.allow(/404/);
  await useFixture(page, "m1");
  await failFile(page, "overview.json", "missing");
  await failFile(page, "health.json", "invalid_json");
  await failFile(page, "tickers/AAPL.json", "schema_version");
  await gotoRoute(page);

  expect((await fetchData(page, "overview.json")).status).toBe(404);
  expect((await fetchData(page, "health.json")).body).toBe("{oups");
  expect(JSON.parse((await fetchData(page, "tickers/AAPL.json")).body)).toEqual({ schema_version: 2 });
  expect(JSON.parse((await fetchData(page, "manifest.json")).body)).toMatchObject({ schema_version: 1 });
});

test.fail("une erreur console non autorisée fait échouer le test", async ({ page }) => {
  await gotoRoute(page);
  await page.evaluate(() => {
    console.error("erreur volontaire");
  });
});

test.fail("une exception non interceptée fait échouer le test", async ({ page }) => {
  await gotoRoute(page);
  await page.evaluate(() => {
    setTimeout(() => {
      throw new Error("exception volontaire");
    }, 0);
  });
  await page.waitForTimeout(50);
});
