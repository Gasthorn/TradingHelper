/** Requêtes de données (spec F09 — R2). */
import { type Page, type Request } from "@playwright/test";

import manifest from "../tests/fixtures/m1/manifest.json" with { type: "json" };
import { expect, gotoRoute, test, useFixture } from "./support";

/** Requêtes `…/data/…` de la page, dans l'ordre. */
function dataRequests(page: Page): Request[] {
  const requests: Request[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.includes("/data/")) requests.push(request);
  });
  return requests;
}

/** Chemin relatif à `data/`. */
const dataPath = (request: Request) => new URL(request.url()).pathname.split("/data/")[1] ?? "";

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

test("chaque fichier hors manifest porte ?v= égal à son empreinte dans le manifest", async ({ page }) => {
  const requests = dataRequests(page);
  await useFixture(page, "m1");
  await gotoRoute(page);
  await expect(page.getByRole("table", { name: /Cours/ })).toBeVisible();
  await gotoRoute(page, "#/ticker/AAPL");
  await expect(page.getByTestId("price-chart")).toHaveAttribute("data-bars", /\d+/);

  const hashes = new Map(manifest.files.map((f) => [f.path, f.sha256]));
  const files = requests.filter((r) => dataPath(r) !== "manifest.json");
  expect(files.map(dataPath).sort()).toEqual(["overview.json", "tickers/AAPL.json"]);
  for (const request of files) {
    expect(new URL(request.url()).searchParams.get("v"), dataPath(request)).toBe(hashes.get(dataPath(request)));
  }
});

test("le manifest est demandé sans empreinte, avec cache: \"no-cache\"", async ({ page }) => {
  // Le mode de cache n'apparaît pas dans les en-têtes vus par Playwright : on observe l'appel à fetch.
  await page.addInitScript(() => {
    const calls: { url: string; cache: string | null }[] = [];
    (window as unknown as { fetchCalls: typeof calls }).fetchCalls = calls;
    const original = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      calls.push({ url, cache: init?.cache ?? null });
      return original(input, init);
    };
  });
  await useFixture(page, "m1");
  await gotoRoute(page);
  await expect(page.getByRole("table", { name: /Cours/ })).toBeVisible();

  const calls = await page.evaluate(() => (window as unknown as { fetchCalls: { url: string; cache: string | null }[] }).fetchCalls);
  expect(calls).toEqual([
    { url: "/data/manifest.json", cache: "no-cache" },
    { url: `/data/overview.json?v=${manifest.files.find((f) => f.path === "overview.json")?.sha256 ?? ""}`, cache: null },
  ]);
});

test("un fichier déjà chargé n'est pas redemandé pendant la visite", async ({ page }) => {
  const requests = dataRequests(page);
  await useFixture(page, "m1");
  await gotoRoute(page, "#/ticker/AAPL");
  await expect(page.getByTestId("price-chart")).toHaveAttribute("data-bars", /\d+/);
  await gotoRoute(page, "#/");
  await expect(page.getByRole("table", { name: /Cours/ })).toBeVisible();
  await gotoRoute(page, "#/ticker/AAPL");
  await expect(page.getByTestId("price-chart")).toHaveAttribute("data-bars", /\d+/);
  await gotoRoute(page, "#/");
  await expect(page.getByRole("table", { name: /Cours/ })).toBeVisible();

  expect(requests.map(dataPath).sort()).toEqual(["manifest.json", "overview.json", "tickers/AAPL.json"]);
});
