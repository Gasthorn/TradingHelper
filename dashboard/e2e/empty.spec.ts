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

test("fixture m1 : indicateurs, classement et derniers signaux en état vide (R4, R13 en M1)", async ({ page }) => {
  await useFixture(page, "m1");
  await gotoRoute(page);

  for (const [heading, text] of [
    ["Indicateurs clés", "Aucune stratégie suivie pour l'instant."],
    ["Classement des stratégies", "Aucune stratégie suivie pour l'instant."],
    ["Derniers signaux", "Aucun signal pour l'instant."],
  ] as const) {
    const section = page.getByRole("region", { name: heading });
    await expect(section).toBeVisible();
    await expect(section).toContainText(text);
  }
});
