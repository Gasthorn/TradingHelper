import { describe, expect, it } from "vitest";

import { THEME_KEY, THEME_PREFERENCES, nextPreference, parsePreference, resolveTheme } from "./theme";

describe("THEME_KEY (R7)", () => {
  it("est stable : le script inline de index.html lit la même clé", () => {
    expect(THEME_KEY).toBe("th-theme");
  });
});

describe("parsePreference (R7)", () => {
  it.each(["light", "dark", "system"] as const)("accepte %s", (value) => {
    expect(parsePreference(value)).toBe(value);
  });

  it.each([null, "", "Dark", "auto", "sombre"])("ramène %j à system (défaut)", (raw) => {
    expect(parsePreference(raw)).toBe("system");
  });
});

describe("resolveTheme (R7)", () => {
  it.each([
    ["light", false, "light"],
    ["light", true, "light"],
    ["dark", false, "dark"],
    ["dark", true, "dark"],
    ["system", false, "light"],
    ["system", true, "dark"],
  ] as const)("%s avec prefers-dark=%s → %s", (pref, prefersDark, expected) => {
    expect(resolveTheme(pref, prefersDark)).toBe(expected);
  });
});

describe("nextPreference (bascule à trois états, Q9)", () => {
  it("parcourt système → clair → sombre → système", () => {
    expect(THEME_PREFERENCES).toEqual(["system", "light", "dark"]);
    expect(nextPreference("system")).toBe("light");
    expect(nextPreference("light")).toBe("dark");
    expect(nextPreference("dark")).toBe("system");
  });
});
