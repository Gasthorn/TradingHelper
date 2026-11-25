/** États vides (spec F09 — R4). */
import { expect, gotoRoute, test, useFixture } from "./support";

test("fixture empty : l'Overview affiche « Aucune donnée disponible »", async ({ page }) => {
  await useFixture(page, "empty");
  await gotoRoute(page);

  await expect(page.getByText("Aucune donnée disponible")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("fixture empty : aucun fichier hors manifest n'est demandé", async ({ page }) => {
  const requested: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/data/")) requested.push(new URL(request.url()).pathname);
  });
  await useFixture(page, "empty");
  await gotoRoute(page);
  await expect(page.getByText("Aucune donnée disponible")).toBeVisible();

  expect(requested).toEqual(["/data/manifest.json"]);
});
