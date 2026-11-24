// Génère les types TypeScript du dashboard depuis les JSON Schemas (spec F08 — R5).
// `npm run gen:types` : un fichier src/types/{nom}.ts par schemas/{nom}.schema.json.
// Les schémas sont eux-mêmes générés par `uv run th schemas` depuis schemas.py : ne jamais
// modifier ni les uns ni les autres à la main. La CI vérifie que la régénération ne produit
// aucun diff.
import { readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import process from "node:process";
import { URL, fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const SCHEMAS_DIR = new URL("../../schemas/", import.meta.url);
const TYPES_DIR = new URL("../src/types/", import.meta.url);
const SUFFIX = ".schema.json";
const GENERATED_MARK = "Généré par `npm run gen:types`";

/**
 * Retire le `title` que pydantic met sur chaque propriété : json-schema-to-typescript en ferait
 * un alias exporté par champ (`export type Date = string[]`), qui masquerait les types globaux
 * `Date` et `Symbol`. Les titres des modèles (racine et `$defs`) sont conservés : ils nomment
 * les interfaces.
 */
function stripPropertyTitles(node) {
  if (Array.isArray(node)) {
    node.forEach(stripPropertyTitles);
  } else if (node !== null && typeof node === "object") {
    if (node.properties !== null && typeof node.properties === "object") {
      for (const property of Object.values(node.properties)) delete property.title;
    }
    Object.values(node).forEach(stripPropertyTitles);
  }
  return node;
}

/** En-tête de chaque fichier généré (repère aussi les fichiers orphelins à supprimer). */
function banner(schemaFile) {
  return `/* ${GENERATED_MARK} depuis schemas/${schemaFile} — ne pas modifier. */`;
}

async function main() {
  const schemaFiles = readdirSync(SCHEMAS_DIR)
    .filter((name) => name.endsWith(SUFFIX))
    .sort();
  if (schemaFiles.length === 0) {
    process.stderr.write("gen-types: aucun schéma dans schemas/ (lancer `uv run th schemas`).\n");
    process.exit(1);
  }

  const written = new Set();
  for (const schemaFile of schemaFiles) {
    const schema = stripPropertyTitles(
      JSON.parse(readFileSync(new URL(schemaFile, SCHEMAS_DIR), "utf8")),
    );
    const name = schemaFile.slice(0, -SUFFIX.length);
    const source = await compile(schema, schema.title ?? name, {
      bannerComment: banner(schemaFile),
      cwd: fileURLToPath(SCHEMAS_DIR),
      declareExternallyReferenced: true,
    });
    const target = `${name}.ts`;
    writeFileSync(new URL(target, TYPES_DIR), source.replace(/\r\n/g, "\n"), "utf8");
    written.add(target);
  }

  // Un schéma supprimé ne doit pas laisser de type orphelin.
  for (const entry of readdirSync(TYPES_DIR)) {
    if (written.has(entry) || !entry.endsWith(".ts")) continue;
    const text = readFileSync(new URL(entry, TYPES_DIR), "utf8");
    if (text.includes(GENERATED_MARK)) rmSync(new URL(entry, TYPES_DIR));
  }
  process.stdout.write(`gen-types: ${written.size} fichier(s) dans src/types/\n`);
}

await main();
