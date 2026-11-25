/** Fichiers de données absents, illisibles ou d'une autre version (spec F09 — R3). */
import { DISCLAIMER, type Failure, expect, failFile, gotoRoute, test, useFixture } from "./support";

const CASES: { file: string; failure: Failure; text: RegExp }[] = [
  { file: "manifest.json", failure: "missing", text: /indisponible/ },
  { file: "overview.json", failure: "missing", text: /indisponible/ },
  { file: "overview.json", failure: "invalid_json", text: /illisible/ },
  { file: "overview.json", failure: "schema_version", text: /version/i },
  { file: "manifest.json", failure: "schema_version", text: /version/i },
];

for (const { file, failure, text } of CASES) {
  test(`${file} (${failure}) : message nommant le fichier, bandeau et navigation conservés`, async ({
    page,
    consoleErrors,
  }) => {
    consoleErrors.allow(/404/); // « Failed to load resource » émis par le navigateur pour un 404 voulu
    await useFixture(page, "m1");
    await failFile(page, file, failure);
    await gotoRoute(page);

    const alert = page.getByRole("alert");
    await expect(alert).toContainText(`data/${file}`);
    await expect(alert).toContainText(text);
    await expect(page.getByRole("note")).toHaveText(DISCLAIMER);
    await expect(page.getByRole("banner").getByRole("link", { name: "TradingHelper" })).toBeVisible();
  });
}

test("une erreur de données n'empêche pas la navigation", async ({ page, consoleErrors }) => {
  consoleErrors.allow(/404/);
  await useFixture(page, "m1");
  await failFile(page, "overview.json", "missing");
  await gotoRoute(page);
  await expect(page.getByRole("alert")).toBeVisible();

  await page.evaluate(() => {
    window.location.hash = "#/inconnu";
  });
  await expect(page.getByRole("heading", { level: 1, name: "Page introuvable" })).toBeVisible();
});
