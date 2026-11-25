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
