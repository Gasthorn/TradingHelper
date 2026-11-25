import { describe, expect, it, vi } from "vitest";

import type { ManifestFile } from "../types/export_manifest";
import { DataError, EXPECTED_SCHEMA_VERSION, type FetchFn, createDataLoader } from "./loader";

const MANIFEST: ManifestFile = {
  schema_version: 1,
  generated_at: "2026-11-23T22:50:12Z",
  data_as_of: "2026-11-23",
  git_sha: null,
  currency: "USD",
  benchmark: "SPY",
  tickers: [],
  strategies: [],
  files: [
    { path: "overview.json", sha256: "9f2c4e1a7b3d5c60", bytes: 10 },
    { path: "tickers/AAPL.json", sha256: "1a2b3c4d5e6f7a8b", bytes: 20 },
  ],
};

type Responder = (url: string) => Response;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** `fetch` simulé : enregistre chaque appel (URL, options) et répond selon `routes`. */
function fakeFetch(routes: Record<string, Responder>) {
  // Les options (2e argument) sont enregistrées par vi.fn dans mock.calls.
  return vi.fn<FetchFn>((url) => {
    const route = routes[url];
    return Promise.resolve(route === undefined ? new Response("not found", { status: 404 }) : route(url));
  });
}

const BASE = "/TradingHelper/";
const MANIFEST_URL = "/TradingHelper/data/manifest.json";
const OVERVIEW_URL = "/TradingHelper/data/overview.json?v=9f2c4e1a7b3d5c60";

async function dataError(promise: Promise<unknown>): Promise<DataError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof DataError) return error;
    throw error;
  }
  throw new Error("aucune erreur levée");
}

describe("EXPECTED_SCHEMA_VERSION", () => {
  it("correspond à la version des types générés", () => {
    expect(EXPECTED_SCHEMA_VERSION).toBe(1);
  });
});

describe("loadManifest (R2)", () => {
  it("demande le manifest sous la base, sans empreinte, en no-cache", async () => {
    const fetchFn = fakeFetch({ [MANIFEST_URL]: () => json(MANIFEST) });
    const loader = createDataLoader(BASE, fetchFn);

    await expect(loader.loadManifest()).resolves.toEqual(MANIFEST);
    expect(fetchFn).toHaveBeenCalledTimes(1);
    expect(fetchFn.mock.calls[0]?.[0]).toBe(MANIFEST_URL);
    expect(fetchFn.mock.calls[0]?.[1]).toMatchObject({ cache: "no-cache" });
  });

  it("ne le demande qu'une fois par visite", async () => {
    const fetchFn = fakeFetch({ [MANIFEST_URL]: () => json(MANIFEST) });
    const loader = createDataLoader(BASE, fetchFn);

    await loader.loadManifest();
    await loader.loadManifest();
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it("lève DataError missing si le manifest est absent (R3)", async () => {
    const loader = createDataLoader(BASE, fakeFetch({}));
    const error = await dataError(loader.loadManifest());
    expect(error.kind).toBe("missing");
    expect(error.path).toBe("manifest.json");
    expect(error.message).toContain("manifest.json");
  });
});

describe("loadFile (R2)", () => {
  it("demande le fichier à l'URL ?v= du manifest, sans option de cache", async () => {
    const fetchFn = fakeFetch({ [OVERVIEW_URL]: () => json({ schema_version: 1, tickers: [] }) });
    const loader = createDataLoader(BASE, fetchFn);

    await expect(loader.loadFile(MANIFEST, "overview.json")).resolves.toEqual({ schema_version: 1, tickers: [] });
    expect(fetchFn.mock.calls[0]?.[0]).toBe(OVERVIEW_URL);
  });

  it("ne redemande pas un fichier déjà chargé", async () => {
    const fetchFn = fakeFetch({ [OVERVIEW_URL]: () => json({ schema_version: 1 }) });
    const loader = createDataLoader(BASE, fetchFn);

    const [a, b] = await Promise.all([
      loader.loadFile(MANIFEST, "overview.json"),
      loader.loadFile(MANIFEST, "overview.json"),
    ]);
    await loader.loadFile(MANIFEST, "overview.json");
    expect(a).toBe(b);
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it("réessaie après un échec (l'erreur n'est pas mise en cache)", async () => {
    let calls = 0;
    const fetchFn = fakeFetch({
      [OVERVIEW_URL]: () => (++calls === 1 ? new Response("", { status: 503 }) : json({ schema_version: 1 })),
    });
    const loader = createDataLoader(BASE, fetchFn);

    await dataError(loader.loadFile(MANIFEST, "overview.json"));
    await expect(loader.loadFile(MANIFEST, "overview.json")).resolves.toEqual({ schema_version: 1 });
  });
});

describe("erreurs typées (R3)", () => {
  it("missing : HTTP 404", async () => {
    const loader = createDataLoader(BASE, fakeFetch({ [OVERVIEW_URL]: () => new Response("", { status: 404 }) }));
    const error = await dataError(loader.loadFile(MANIFEST, "overview.json"));
    expect(error).toMatchObject({ kind: "missing", path: "overview.json" });
    expect(error.message).toContain("overview.json");
  });

  it("missing : chemin absent de manifest.files, sans requête", async () => {
    const fetchFn = fakeFetch({});
    const loader = createDataLoader(BASE, fetchFn);
    const error = await dataError(loader.loadFile(MANIFEST, "tickers/ZZZ.json"));
    expect(error).toMatchObject({ kind: "missing", path: "tickers/ZZZ.json" });
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("missing : échec réseau", async () => {
    const fetchFn = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    const loader = createDataLoader(BASE, fetchFn);
    const error = await dataError(loader.loadFile(MANIFEST, "overview.json"));
    expect(error).toMatchObject({ kind: "missing", path: "overview.json" });
  });

  it("invalid_json : contenu non JSON", async () => {
    const loader = createDataLoader(BASE, fakeFetch({ [OVERVIEW_URL]: () => new Response("{oups", { status: 200 }) }));
    const error = await dataError(loader.loadFile(MANIFEST, "overview.json"));
    expect(error).toMatchObject({ kind: "invalid_json", path: "overview.json" });
  });

  it.each([[[1, 2]], [null], ["texte"]])("invalid_json : JSON qui n'est pas un objet (%j)", async (body) => {
    const loader = createDataLoader(BASE, fakeFetch({ [OVERVIEW_URL]: () => json(body) }));
    const error = await dataError(loader.loadFile(MANIFEST, "overview.json"));
    expect(error.kind).toBe("invalid_json");
  });

  it.each([[{ schema_version: 2 }], [{ tickers: [] }]])("schema_version : version inattendue ou absente (%j)", async (body) => {
    const loader = createDataLoader(BASE, fakeFetch({ [OVERVIEW_URL]: () => json(body) }));
    const error = await dataError(loader.loadFile(MANIFEST, "overview.json"));
    expect(error).toMatchObject({ kind: "schema_version", path: "overview.json" });
  });

  it("schema_version : s'applique aussi au manifest", async () => {
    const loader = createDataLoader(BASE, fakeFetch({ [MANIFEST_URL]: () => json({ ...MANIFEST, schema_version: 2 }) }));
    const error = await dataError(loader.loadManifest());
    expect(error).toMatchObject({ kind: "schema_version", path: "manifest.json" });
  });
});
