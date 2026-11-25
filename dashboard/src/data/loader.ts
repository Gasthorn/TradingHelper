/**
 * Chargement des fichiers de données (spec F09 — R2, R3). Seul module du dashboard qui
 * appelle `fetch`.
 *
 * - `manifest.json` est demandé en premier, en `no-cache` ;
 * - chaque autre fichier est demandé à `<base>data/<path>?v=<sha256>` (cache-busting, F08 R11),
 *   au plus une fois par visite : la promesse est mémorisée, sauf en cas d'échec (réessai possible) ;
 * - toute anomalie lève une `DataError` qui nomme le fichier.
 */
import type { ManifestFile } from "../types/export_manifest";
import { MANIFEST_PATH, dataUrl } from "../lib/urls";

/** Version de contrat attendue, celle des types générés depuis `schemas/`. */
export const EXPECTED_SCHEMA_VERSION: ManifestFile["schema_version"] = 1;

/** `missing` : absent du manifest, HTTP ≠ 2xx ou échec réseau. */
export type DataErrorKind = "missing" | "invalid_json" | "schema_version";

export class DataError extends Error {
  readonly path: string;
  readonly kind: DataErrorKind;

  constructor(path: string, kind: DataErrorKind, detail: string) {
    super(`${MESSAGES[kind]} : data/${path} (${detail})`);
    this.name = "DataError";
    this.path = path;
    this.kind = kind;
  }
}

const MESSAGES: Record<DataErrorKind, string> = {
  missing: "Fichier de données indisponible",
  invalid_json: "Fichier de données illisible",
  schema_version: "Version de fichier de données inattendue",
};

export type FetchFn = (input: string, init?: RequestInit) => Promise<Response>;

export interface DataLoader {
  loadManifest(): Promise<ManifestFile>;
  loadFile<T extends { schema_version: number }>(manifest: ManifestFile, path: string): Promise<T>;
}

/** Lit et vérifie un fichier : HTTP, JSON objet, `schema_version`. */
async function fetchChecked(fetchFn: FetchFn, url: string, path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetchFn(url, init);
  } catch (error) {
    throw new DataError(path, "missing", error instanceof Error ? error.message : "échec réseau");
  }
  if (!response.ok) throw new DataError(path, "missing", `HTTP ${String(response.status)}`);

  let body: unknown;
  try {
    body = JSON.parse(await response.text());
  } catch {
    throw new DataError(path, "invalid_json", "JSON invalide");
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    throw new DataError(path, "invalid_json", "objet JSON attendu");
  }
  const version: unknown = (body as Record<string, unknown>).schema_version;
  if (version !== EXPECTED_SCHEMA_VERSION) {
    const found = version === undefined ? "absente" : JSON.stringify(version);
    throw new DataError(path, "schema_version", `schema_version ${found}, attendue ${String(EXPECTED_SCHEMA_VERSION)}`);
  }
  return body;
}

/** Chargeur avec cache mémoire ; `base` = `import.meta.env.BASE_URL` en production. */
export function createDataLoader(base: string, fetchFn: FetchFn): DataLoader {
  const cache = new Map<string, Promise<unknown>>();

  function remember(key: string, load: () => Promise<unknown>): Promise<unknown> {
    let promise = cache.get(key);
    if (promise === undefined) {
      promise = load();
      cache.set(key, promise);
      promise.catch(() => cache.delete(key));
    }
    return promise;
  }

  return {
    loadManifest() {
      const url = `${base}data/${MANIFEST_PATH}`;
      return remember(MANIFEST_PATH, () =>
        fetchChecked(fetchFn, url, MANIFEST_PATH, { cache: "no-cache" }),
      ) as Promise<ManifestFile>;
    },

    loadFile<T extends { schema_version: number }>(manifest: ManifestFile, path: string): Promise<T> {
      const entry = manifest.files.find((f) => f.path === path);
      if (entry === undefined) {
        return Promise.reject(new DataError(path, "missing", "absent du manifest"));
      }
      return remember(path, () => fetchChecked(fetchFn, dataUrl(base, entry), path)) as Promise<T>;
    },
  };
}

/** Chargeur de l'application (base de déploiement, `fetch` du navigateur). */
export const dataLoader: DataLoader = createDataLoader(import.meta.env.BASE_URL, (input, init) =>
  fetch(input, init),
);
