import { describe, expect, it } from "vitest";

import source from "./dates.ts?raw";
import {
  STALE_AFTER,
  dayNumber,
  freshness,
  fromDayNumber,
  lastAssumedSession,
  periodStart,
  sessionsBehind,
  todayInNewYork,
} from "./dates";

describe("dayNumber / fromDayNumber (dates civiles)", () => {
  it("compte les jours depuis le 1970-01-01", () => {
    expect(dayNumber("1970-01-01")).toBe(0);
    expect(dayNumber("1970-01-02")).toBe(1);
    expect(dayNumber("1969-12-31")).toBe(-1);
  });

  it.each(["2026-11-23", "2024-02-29", "2010-01-04", "2000-12-31", "1999-01-01"])(
    "fait l'aller-retour pour %s",
    (d) => {
      expect(fromDayNumber(dayNumber(d))).toBe(d);
    },
  );

  it("passe correctement le 29 février", () => {
    expect(fromDayNumber(dayNumber("2024-02-28") + 1)).toBe("2024-02-29");
    expect(fromDayNumber(dayNumber("2024-02-29") + 1)).toBe("2024-03-01");
  });

  it("refuse une date mal formée ou inexistante", () => {
    expect(() => dayNumber("2026-11-3")).toThrow(RangeError);
    expect(() => dayNumber("2026-02-30")).toThrow(RangeError);
    expect(() => dayNumber("23/11/2026")).toThrow(RangeError);
  });
});

describe("todayInNewYork (Définitions)", () => {
  it("donne la date civile à New York, pas en UTC ni en heure locale", () => {
    // 03:00 UTC le 24 = 22:00 la veille à New York (heure d'hiver).
    expect(todayInNewYork(new Date("2026-11-24T03:00:00Z"))).toBe("2026-11-23");
    expect(todayInNewYork(new Date("2026-11-24T05:00:00Z"))).toBe("2026-11-24");
  });

  it("suit l'heure d'été de New York", () => {
    // 03:30 UTC le 1er juillet = 23:30 le 30 juin à New York (UTC−4).
    expect(todayInNewYork(new Date("2026-07-01T03:30:00Z"))).toBe("2026-06-30");
  });
});

describe("lastAssumedSession — S' (Définitions)", () => {
  it.each([
    ["2026-11-24", "2026-11-23"], // mardi → lundi
    ["2026-11-23", "2026-11-20"], // lundi → vendredi précédent
    ["2026-11-28", "2026-11-27"], // samedi → vendredi
    ["2026-11-29", "2026-11-27"], // dimanche → vendredi
    ["2026-11-27", "2026-11-26"], // la séance du jour n'est jamais exigée (Thanksgiving compté)
  ])("le %s donne %s", (today, expected) => {
    expect(lastAssumedSession(today)).toBe(expected);
  });
});

describe("sessionsBehind (Définitions, R6)", () => {
  it("vaut 0 quand la donnée est à jour ou en avance sur S'", () => {
    expect(sessionsBehind("2026-11-23", "2026-11-24")).toBe(0);
    expect(sessionsBehind("2026-11-24", "2026-11-24")).toBe(0);
  });

  it("compte les jours ouvrés de la même semaine", () => {
    expect(sessionsBehind("2026-11-23", "2026-11-26")).toBe(2); // S' = mer. 25 : 24, 25
  });

  it("ignore le week-end", () => {
    expect(sessionsBehind("2026-11-20", "2026-11-24")).toBe(1); // S' = lun. 23
    expect(sessionsBehind("2026-11-20", "2026-11-30")).toBe(5); // S' = ven. 27
  });

  it("compte un jour férié comme une séance (approximation Q2)", () => {
    // Thanksgiving, jeudi 2026-11-26 : compté.
    expect(sessionsBehind("2026-11-25", "2026-11-30")).toBe(2); // 26, 27
  });

  it("reste exact sur plusieurs années", () => {
    // 2010-01-04 (lundi) → S' = 2026-11-20 (vendredi) : 882 semaines + 4 jours ouvrés.
    const days = dayNumber("2026-11-20") - dayNumber("2010-01-04");
    let expected = 0;
    for (let n = 1; n <= days; n++) {
      const weekday = (dayNumber("2010-01-04") + n + 4) % 7; // 0 = dimanche
      if (weekday !== 0 && weekday !== 6) expected++;
    }
    expect(sessionsBehind("2010-01-04", "2026-11-23")).toBe(expected);
  });
});

describe("freshness (R6)", () => {
  it("seuil de 3 séances, comme F02", () => {
    expect(STALE_AFTER).toBe(3);
  });

  it("signale l'absence de données", () => {
    expect(freshness(null, "2026-11-30")).toEqual({ kind: "none" });
  });

  it("n'alerte pas à 3 séances de retard", () => {
    // data_as_of lun. 23 ; aujourd'hui ven. 27 → S' = jeu. 26 → 24, 25, 26.
    expect(freshness("2026-11-23", "2026-11-27")).toEqual({ kind: "fresh", behind: 3 });
  });

  it("alerte à 4 séances de retard", () => {
    // aujourd'hui lun. 30 → S' = ven. 27 → 24, 25, 26, 27.
    expect(freshness("2026-11-23", "2026-11-30")).toEqual({ kind: "stale", behind: 4 });
  });

  it("est à jour le lendemain de la séance", () => {
    expect(freshness("2026-11-23", "2026-11-24")).toEqual({ kind: "fresh", behind: 0 });
  });
});

describe("periodStart (R16)", () => {
  it.each([
    ["1M", "2026-10-23"],
    ["6M", "2026-05-23"],
    ["1A", "2025-11-23"],
    ["5A", "2021-11-23"],
  ] as const)("%s depuis le 2026-11-23 → %s", (period, expected) => {
    expect(periodStart("2026-11-23", period)).toBe(expected);
  });

  it("Max n'a pas de borne", () => {
    expect(periodStart("2026-11-23", "Max")).toBeNull();
  });

  it("borne le jour à la fin d'un mois plus court", () => {
    expect(periodStart("2026-03-31", "1M")).toBe("2026-02-28");
    expect(periodStart("2024-03-31", "1M")).toBe("2024-02-29");
    expect(periodStart("2026-05-31", "6M")).toBe("2025-11-30");
    expect(periodStart("2024-02-29", "1A")).toBe("2023-02-28");
  });

  it("traverse le changement d'année", () => {
    expect(periodStart("2026-01-15", "1M")).toBe("2025-12-15");
  });
});

describe("aucune conversion implicite en instant (R11)", () => {
  it("le module ne construit jamais une Date depuis une chaîne", () => {
    // Code seul : les commentaires citent justement l'exemple à éviter.
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    expect(code).not.toMatch(/new Date\(\s*["'`]/);
    expect(code).not.toMatch(/Date\.parse\(/);
    expect(code).not.toMatch(/new Date\(\s*[a-zA-Z_$][\w$]*\s*\)/);
  });

  it("ne décale pas une date de séance, quel que soit le fuseau du poste", () => {
    for (const d of ["2026-11-23", "2026-03-08", "2026-11-01", "2026-01-01"]) {
      expect(fromDayNumber(dayNumber(d))).toBe(d);
      expect(fromDayNumber(dayNumber(d) + 1)).not.toBe(d);
    }
  });
});
