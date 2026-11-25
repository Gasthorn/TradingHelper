/** Accessibilité : contrastes WCAG AA dans les deux thèmes, focus visible (spec F09 — R8). */
import AxeBuilder from "@axe-core/playwright";

import { expect, gotoRoute, test, useFixture } from "./support";

for (const colorScheme of ["light", "dark"] as const) {
  for (const hash of ["#/", "#/inconnu", "#/ticker/AAPL"]) {
    test(`aucune violation de contraste sur ${hash} en thème ${colorScheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme });
      await useFixture(page, "m1");
      await gotoRoute(page, hash);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

      const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze();
      expect(results.violations.flatMap((v) => v.nodes.map((n) => `${n.target.join(" ")} : ${n.failureSummary ?? ""}`))).toEqual([]);
    });
  }
}

test("le focus clavier est visible sur la bascule de thème", async ({ page }) => {
  await useFixture(page, "m1");
  await gotoRoute(page);
  const button = page.getByRole("button", { name: /Thème/ });

  for (let i = 0; i < 10 && !(await button.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(button).toBeFocused();
  const outline = await button.evaluate((el) => {
    const style = getComputedStyle(el);
    return { style: style.outlineStyle, width: parseFloat(style.outlineWidth) };
  });
  expect(outline.style).not.toBe("none");
  expect(outline.width).toBeGreaterThanOrEqual(2);
});
