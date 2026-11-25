/** Page Overview (spec F09 — R12, R8). Valeurs attendues lues dans la fixture `m1`. */
import manifest from "../tests/fixtures/m1/manifest.json" with { type: "json" };
import overview from "../tests/fixtures/m1/overview.json" with { type: "json" };
import { changeParts, formatPrice } from "../src/lib/format";
import { expect, gotoRoute, test, useFixture } from "./support";

test.beforeEach(async ({ page }) => {
  await useFixture(page, "m1");
  await gotoRoute(page);
});

const rows = (page: import("@playwright/test").Page) => page.getByRole("table", { name: /Cours/ }).locator("tbody tr");

test("une ligne par symbole, dans l'ordre du manifest, avec sparkline", async ({ page }) => {
  await expect(rows(page)).toHaveCount(manifest.tickers.length);

  for (const [index, ticker] of manifest.tickers.entries()) {
    const row = rows(page).nth(index);
    const data = overview.tickers.find((t) => t.symbol === ticker.symbol);
    if (data === undefined) throw new Error(`${ticker.symbol} absent de overview.json`);

    await expect(row.getByRole("link", { name: ticker.symbol, exact: true })).toBeVisible();
    await expect(row).toContainText(ticker.name);
    await expect(row).toContainText(formatPrice(data.last_close));
    await expect(row).toContainText(changeParts(data.change_1d).text);
    await expect(row.locator("svg")).toHaveCount(1);
    await expect(row.getByRole("img")).toHaveAttribute("aria-label", new RegExp(`${String(data.spark.length)} dernières séances`));
  }
});

test("la variation porte un signe et une flèche, pas seulement une couleur (R8)", async ({ page }) => {
  for (const [index, ticker] of manifest.tickers.entries()) {
    const data = overview.tickers.find((t) => t.symbol === ticker.symbol);
    const parts = changeParts(data?.change_1d ?? null);
    const cell = rows(page).nth(index).locator(".change");
    await expect(cell).toHaveText(`${parts.arrow} ${parts.text}`.trim());
    await expect(cell).toHaveAttribute("data-direction", parts.direction);
  }
});

test("le benchmark est signalé « indice de référence »", async ({ page }) => {
  const benchmark = manifest.tickers.find((t) => t.benchmark);
  expect(benchmark?.symbol).toBe("SPY");

  await expect(rows(page).filter({ hasText: "SPY" })).toContainText("indice de référence");
  await expect(rows(page).filter({ hasText: "indice de référence" })).toHaveCount(1);
});

test("une ligne mène à la fiche du symbole", async ({ page }) => {
  await rows(page).filter({ hasText: "BRK.B" }).getByRole("link", { name: "BRK.B" }).click();

  await expect(page).toHaveURL(/#\/ticker\/BRK\.B$/);
  await expect(page.getByRole("heading", { level: 1, name: "BRK.B" })).toBeVisible();
});
