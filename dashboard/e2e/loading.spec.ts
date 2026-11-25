/** Requêtes de données (spec F09 — R2). */
import { expect, gotoRoute, test, useFixture } from "./support";

test("l'Overview ne charge que manifest.json et overview.json (aucun tickers/*)", async ({ page }) => {
  const requested: string[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (pathname.includes("/data/")) requested.push(pathname);
  });
  await useFixture(page, "m1");
  await gotoRoute(page);
  await expect(page.getByRole("table", { name: /Cours/ }).locator("tbody tr")).toHaveCount(4);

  expect(requested.sort()).toEqual(["/data/manifest.json", "/data/overview.json"]);
});

test("le module du graphique n'est chargé que sur la page Ticker", async ({ page }) => {
  const scripts: string[] = [];
  page.on("request", (request) => {
    if (request.resourceType() === "script") scripts.push(new URL(request.url()).pathname);
  });
  await useFixture(page, "m1");
  await gotoRoute(page);
  await expect(page.getByRole("table", { name: /Cours/ })).toBeVisible();
  await gotoRoute(page, "#/inconnu");
  await expect(page.getByRole("heading", { name: "Page introuvable" })).toBeVisible();
  const before = [...scripts];

  await gotoRoute(page, "#/ticker/AAPL");
  await expect(page.getByTestId("price-chart")).toHaveAttribute("data-bars", /\d+/);

  expect(before.filter((p) => p.includes("priceChart"))).toEqual([]);
  expect(scripts.filter((p) => p.includes("priceChart"))).toHaveLength(1);
});
