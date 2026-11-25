/**
 * Hooks de chargement (spec F09 — R2, R3) : état `loading` | `ok` | `error` d'un fichier de
 * données. Un résultat arrivé après un changement de page ou de paramètre est ignoré.
 */
import { useEffect, useState } from "preact/hooks";

import type { ManifestFile } from "../types/export_manifest";
import { dataLoader } from "./loader";

export type Loaded<T> =
  | { status: "loading" }
  | { status: "ok"; data: T }
  | { status: "error"; error: Error };

function useAsync<T>(load: () => Promise<T>, deps: readonly unknown[]): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ status: "loading" });
  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    load().then(
      (data) => {
        if (current) setState({ status: "ok", data });
      },
      (error: unknown) => {
        if (current) setState({ status: "error", error: error instanceof Error ? error : new Error(String(error)) });
      },
    );
    return () => {
      current = false;
    };
  }, deps); // `deps` décrit `load`
  return state;
}

/** Manifest (chargé une fois par visite). */
export function useManifest(): Loaded<ManifestFile> {
  return useAsync(() => dataLoader.loadManifest(), []);
}

/** Fichier `path` du manifest. */
export function useFile<T extends { schema_version: number }>(manifest: ManifestFile, path: string): Loaded<T> {
  return useAsync(() => dataLoader.loadFile<T>(manifest, path), [manifest, path]);
}
