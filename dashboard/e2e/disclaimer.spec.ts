/** Bandeau d'avertissement P8 (spec F09 — R5). */
import { DISCLAIMER, expect, gotoRoute, test } from "./support";

test("le texte exact de P8 est affiché sur l'accueil", async ({ page }) => {
  await gotoRoute(page);

  await expect(page.getByRole("note")).toHaveText(DISCLAIMER);
});
