/** Page Ticker (spec F09 — R14–R18 en M1). Graphique lu via ses attributs data-* (décision 3 du plan). */
import aapl from "../tests/fixtures/m1/tickers/AAPL.json" with { type: "json" };
import { periodWindow } from "../src/lib/series";
import { expect, gotoRoute, test, useFixture } from "./support";

test.describe("résolution du symbole (R14)", () => {
  test("#/ticker/brk.b résout BRK.B sans tenir compte de la casse", async ({ page }) => {
    await useFixture(page, "m1");
    await gotoRoute(page, "#/ticker/brk.b");

    await expect(page.getByRole("heading", { level: 1, name: "BRK.B" })).toBeVisible();
    await expect(page.getByText("Berkshire Hathaway Inc. (Class B)")).toBeVisible();
  });

  test("symbole inconnu : « Pas de données pour ZZZ », sans requête tickers/ZZZ.json", async ({ page }) => {
    const requested: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/data/")) requested.push(new URL(request.url()).pathname);
    });
    await useFixture(page, "m1");
    await gotoRoute(page, "#/ticker/ZZZ");

    await expect(page.getByText("Pas de données pour ZZZ")).toBeVisible();
    expect(requested).toEqual(["/data/manifest.json"]);
  });

  test("charge le fichier du symbole et lui seul", async ({ page }) => {
    const requested: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/data/")) requested.push(new URL(request.url()).pathname);
    });
    await useFixture(page, "m1");
    await gotoRoute(page, "#/ticker/AAPL");
    await expect(page.getByRole("radiogroup", { name: "Période" })).toBeVisible();

    expect(requested.sort()).toEqual(["/data/manifest.json", "/data/tickers/AAPL.json"]);
  });
});

test.describe("sélecteurs (R16, R4)", () => {
  test.beforeEach(async ({ page }) => {
    await useFixture(page, "m1");
    await gotoRoute(page, "#/ticker/AAPL");
  });

  test("période : 1M, 6M, 1A, 5A, Max, 6M par défaut", async ({ page }) => {
    const group = page.getByRole("radiogroup", { name: "Période" });
    await expect(group.getByRole("radio")).toHaveCount(5);
    for (const label of ["1M", "6M", "1A", "5A", "Max"]) {
      await expect(group.getByRole("radio", { name: label, exact: true })).toBeVisible();
    }
    await expect(group.getByRole("radio", { name: "6M" })).toBeChecked();

    await group.getByText("1M", { exact: true }).click();
    await expect(group.getByRole("radio", { name: "1M" })).toBeChecked();
    await expect(group.getByRole("radio", { name: "6M" })).not.toBeChecked();
  });

  test("overlays : SMA20 et SMA50 actives, SMA200 et Bollinger inactives au premier affichage", async ({ page }) => {
    const group = page.getByRole("group", { name: "Indicateurs" });
    await expect(group.getByRole("checkbox", { name: "SMA20", exact: true })).toBeChecked();
    await expect(group.getByRole("checkbox", { name: "SMA50", exact: true })).toBeChecked();
    await expect(group.getByRole("checkbox", { name: "SMA200", exact: true })).not.toBeChecked();
    await expect(group.getByRole("checkbox", { name: "Bollinger", exact: true })).not.toBeChecked();
  });

  test("fixture m1 sans marqueur : sélecteur de stratégie masqué", async ({ page }) => {
    await expect(page.getByRole("radiogroup", { name: "Période" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Stratégie" })).toHaveCount(0);
  });

  test("fiche « Signal du jour » en état vide (M1)", async ({ page }) => {
    const card = page.getByRole("region", { name: "Signal du jour" });
    await expect(card).toContainText("Aucun signal pour l'instant.");
  });
});

test("fixture m1-signals : sélecteur de stratégie visible avec les stratégies des marqueurs", async ({ page }) => {
  await useFixture(page, "m1-signals");
  await gotoRoute(page, "#/ticker/AAPL");

  const select = page.getByRole("combobox", { name: "Stratégie" });
  await expect(select).toBeVisible();
  await expect(select.getByRole("option")).toHaveText(["Toutes", "lgbm_dir5_v3"]);
});

test("tickers/AAPL.json absent : message nommant le fichier", async ({ page, consoleErrors }) => {
  consoleErrors.allow(/404/);
  await useFixture(page, "m1");
  await page.route("**/data/tickers/AAPL.json*", (route) => route.fulfill({ status: 404, body: "" }));
  await gotoRoute(page, "#/ticker/AAPL");

  await expect(page.getByRole("alert")).toContainText("data/tickers/AAPL.json");
});

test.describe("graphique de prix (R15, R16, R8)", () => {
  const chart = (page: import("@playwright/test").Page) => page.getByTestId("price-chart");

  test.beforeEach(async ({ page }) => {
    await useFixture(page, "m1");
  });

  test("affiche les barres de la période 6M par défaut, dans un canvas", async ({ page }) => {
    await gotoRoute(page, "#/ticker/AAPL");
    const w = periodWindow(aapl.series.date, "6M");

    await expect(chart(page)).toHaveAttribute("data-bars", String(w.to - w.from + 1));
    await expect(chart(page)).toHaveAttribute("data-first-date", aapl.series.date[w.from] ?? "");
    await expect(chart(page)).toHaveAttribute("data-last-date", "2026-11-23");
    await expect(chart(page).locator("canvas").first()).toBeVisible();
  });

  test("1M : première barre au 2026-10-23 ou après", async ({ page }) => {
    await gotoRoute(page, "#/ticker/AAPL");
    await page.getByRole("radiogroup", { name: "Période" }).getByText("1M", { exact: true }).click();

    const w = periodWindow(aapl.series.date, "1M");
    await expect(chart(page)).toHaveAttribute("data-first-date", aapl.series.date[w.from] ?? "");
    expect((aapl.series.date[w.from] ?? "") >= "2026-10-23").toBe(true);
  });

  test("Max : toute la série", async ({ page }) => {
    await gotoRoute(page, "#/ticker/AAPL");
    await page.getByRole("radiogroup", { name: "Période" }).getByText("Max", { exact: true }).click();

    await expect(chart(page)).toHaveAttribute("data-bars", String(aapl.series.date.length));
  });

  test("overlays : SMA20 et SMA50 tracées par défaut, Bollinger ajoutée à la demande", async ({ page }) => {
    await gotoRoute(page, "#/ticker/AAPL");
    await expect(chart(page)).toHaveAttribute("data-overlays", "sma20,sma50");

    await page.getByRole("checkbox", { name: "Bollinger", exact: true }).check();
    await expect(chart(page)).toHaveAttribute("data-overlays", "sma20,sma50,bollinger");
    await page.getByRole("checkbox", { name: "SMA20", exact: true }).uncheck();
    await expect(chart(page)).toHaveAttribute("data-overlays", "sma50,bollinger");
  });

  test("historique court : SMA200 désactivée, « historique insuffisant »", async ({ page }) => {
    await gotoRoute(page, "#/ticker/BRK.B");
    const sma200 = page.getByRole("checkbox", { name: /SMA200/ });

    await expect(sma200).toBeDisabled();
    await expect(page.getByRole("group", { name: "Indicateurs" })).toContainText("historique insuffisant");
    await expect(chart(page)).toHaveAttribute("data-overlays", "sma20,sma50");
  });

  test("bougies haussières creuses, baissières pleines (R8)", async ({ page }) => {
    await gotoRoute(page, "#/ticker/AAPL");
    await expect(chart(page)).toHaveAttribute("data-up-style", "hollow");
    await expect(chart(page)).toHaveAttribute("data-down-style", "filled");
  });

  test("panneau RSI séparé avec les lignes 30 et 70", async ({ page }) => {
    await gotoRoute(page, "#/ticker/AAPL");
    await expect(chart(page)).toHaveAttribute("data-panes", "2");
    await expect(chart(page)).toHaveAttribute("data-rsi-lines", "30,70");
  });
});
