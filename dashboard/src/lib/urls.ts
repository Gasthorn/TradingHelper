/**
 * URL des fichiers de données du dashboard (spec F09 — R2, R10). Module pur : la base est
 * toujours passée en paramètre (`import.meta.env.BASE_URL` côté appelant).
 */

/** Chemin du manifest, relatif au dossier `data/` ; chargé sans empreinte, en `no-cache`. */
export const MANIFEST_PATH = "manifest.json";

/** Entrée de `manifest.files` : chemin relatif à `data/` et empreinte (16 caractères hex). */
export interface DataFileRef {
  readonly path: string;
  readonly sha256: string;
}

/**
 * URL d'un fichier de données : `<base>data/<path>?v=<sha256>` (cache-busting, F08 R11).
 * `base` commence et finit par "/" (garanti par `vite.config.ts`). Les chemins du contrat ne
 * contiennent que [A-Za-z0-9_.-] et "/" : aucun encodage n'est nécessaire.
 */
export function dataUrl(base: string, entry: DataFileRef): string {
  return `${base}data/${entry.path}?v=${entry.sha256}`;
}
