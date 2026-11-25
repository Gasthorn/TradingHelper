/**
 * Outils communs des tests e2e (spec F09 — R25).
 *
 * - `test` : comme celui de Playwright, mais échoue si la page émet une erreur console ou une
 *   exception non interceptée (sauf motifs autorisés par `consoleErrors.allow`) ;
 * - `useFixture` : sert un jeu de `tests/fixtures/<nom>/` à la place de `<base>data/…` ;
 * - `failFile` : simule un fichier absent, illisible ou d'une autre version (R3) ;
 * - `gotoRoute`, `freezeClock` : navigation relative à la base, horloge figée (R6).
 *
 * Les chemins de fichiers sont relatifs au dossier `dashboard/`, répertoire courant de
 * `npm run test:e2e`.
 */
import { type Page, test as base, expect } from "@playwright/test";

/** Texte exact imposé par la constitution (P8). */
export const DISCLAIMER = "Outil expérimental et éducatif. Ceci n'est pas un conseil en investissement.";

export const FIXTURES_DIR = "tests/fixtures";

export type FixtureName = "empty" | "m1" | "m1-signals";

/** Collecte des erreurs de la page ; `allow` tolère des messages attendus (ex. HTTP 404 voulu). */
export interface ConsoleErrors {
  readonly messages: string[];
  allow(pattern: RegExp): void;
}

export const test = base.extend<{ consoleErrors: ConsoleErrors }>({
  consoleErrors: [
    async ({ page }, use) => {
      const messages: string[] = [];
      const allowed: RegExp[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") messages.push(message.text());
      });
      page.on("pageerror", (error) => {
        messages.push(`pageerror: ${error.message}`);
      });
      await use({
        messages,
        allow(pattern) {
          allowed.push(pattern);
        },
      });
      const unexpected = messages.filter((m) => !allowed.some((pattern) => pattern.test(m)));
      expect(unexpected, "erreurs console inattendues").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/** Chemin relatif à `data/` d'une URL de données (`…/data/tickers/AAPL.json?v=…`). */
function dataPath(url: string): string {
  const { pathname } = new URL(url);
  return decodeURIComponent(pathname.slice(pathname.indexOf("/data/") + "/data/".length));
}

/** Sert le jeu `name` pour toutes les requêtes `<base>data/…` ; fichier inconnu → 404. */
export async function useFixture(page: Page, name: FixtureName): Promise<void> {
  await page.route("**/data/**", async (route) => {
    const path = `${FIXTURES_DIR}/${name}/${dataPath(route.request().url())}`;
    try {
      await route.fulfill({ path, contentType: "application/json" });
    } catch {
      await route.fulfill({ status: 404, contentType: "text/plain", body: "not found" });
    }
  });
}

export type Failure = "missing" | "invalid_json" | "schema_version";

/** Remplace la réponse d'un fichier de données (à appeler après `useFixture`, qu'elle supplante). */
export async function failFile(page: Page, path: string, failure: Failure): Promise<void> {
  await page.route(
    (url) => dataPath(url.href) === path,
    async (route) => {
      if (failure === "missing") {
        await route.fulfill({ status: 404, contentType: "text/plain", body: "not found" });
      } else if (failure === "invalid_json") {
        await route.fulfill({ contentType: "application/json", body: "{oups" });
      } else {
        await route.fulfill({ contentType: "application/json", body: '{"schema_version":2}' });
      }
    },
  );
}

/** Ouvre une route du dashboard (`"#/ticker/AAPL"`), relative à la base du projet. */
export async function gotoRoute(page: Page, hash = "#/"): Promise<void> {
  await page.goto(`./${hash}`);
}

/** Fige l'horloge de la page (avant `gotoRoute`). */
export async function freezeClock(page: Page, isoInstant: string): Promise<void> {
  await page.clock.setFixedTime(new Date(isoInstant));
}
