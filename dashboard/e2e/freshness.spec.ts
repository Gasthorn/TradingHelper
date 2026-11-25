/**
 * Date des données et alerte « Données périmées » (spec F09 — R6). Fixture `m1` :
 * data_as_of = lundi 2026-11-23. Horloge figée en heure de New York.
 */
import { expect, freezeClock, gotoRoute, test, useFixture } from "./support";

for (const hash of ["#/", "#/ticker/AAPL", "#/inconnu"]) {
  test(`la date des données est affichée sur ${hash}`, async ({ page }) => {
    await freezeClock(page, "2026-11-24T12:00:00-05:00");
    await useFixture(page, "m1");
    await gotoRoute(page, hash);

    await expect(page.getByRole("banner")).toContainText("Données au 23/11/2026");
  });
}

test("3 séances de retard : pas d'alerte", async ({ page }) => {
  // Vendredi 27 → S' = jeudi 26 (Thanksgiving compté) → 24, 25, 26.
  await freezeClock(page, "2026-11-27T12:00:00-05:00");
  await useFixture(page, "m1");
  await gotoRoute(page);

  await expect(page.getByRole("banner")).toContainText("Données au 23/11/2026");
  await expect(page.getByText(/Données périmées/)).toHaveCount(0);
});

test("4 séances de retard : « Données périmées (4 séances) »", async ({ page }) => {
  // Lundi 30 → S' = vendredi 27 → 24, 25, 26, 27.
  await freezeClock(page, "2026-11-30T12:00:00-05:00");
  await useFixture(page, "m1");
  await gotoRoute(page);

  await expect(page.getByRole("banner").getByRole("status")).toHaveText("Données périmées (4 séances)");
});

test("la date du jour est prise à New York, pas en UTC", async ({ page }) => {
  // 03:00 UTC le samedi 28 = 22:00 le vendredi 27 à New York → S' = jeudi 26 → 3 séances.
  await freezeClock(page, "2026-11-28T03:00:00Z");
  await useFixture(page, "m1");
  await gotoRoute(page);

  await expect(page.getByRole("banner")).toContainText("Données au 23/11/2026");
  await expect(page.getByText(/Données périmées/)).toHaveCount(0);
});

test("fixture empty : aucune date ni alerte, « Aucune donnée disponible »", async ({ page }) => {
  await freezeClock(page, "2026-11-30T12:00:00-05:00");
  await useFixture(page, "empty");
  await gotoRoute(page);

  await expect(page.getByText("Aucune donnée disponible")).toBeVisible();
  await expect(page.getByRole("banner")).not.toContainText("Données au");
  await expect(page.getByText(/Données périmées/)).toHaveCount(0);
});
