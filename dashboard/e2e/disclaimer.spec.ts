/** Bandeau d'avertissement P8 (spec F09 — R5). */
import { DISCLAIMER, expect, gotoRoute, test, useFixture } from "./support";

for (const hash of ["#/", "#/ticker/AAPL", "#/inconnu"]) {
  test(`le texte exact de P8 est affiché sur ${hash}`, async ({ page }) => {
    await useFixture(page, "m1");
    await gotoRoute(page, hash);

    await expect(page.getByRole("note")).toHaveText(DISCLAIMER);
    await expect(page.getByRole("note")).toBeVisible();
  });
}
