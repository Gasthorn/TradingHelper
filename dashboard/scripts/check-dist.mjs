// Vérifie le build du dashboard (spec F00 — R12, R13) : `npm run build && npm run check:dist`.
// Le titre et le bandeau P8 sont en HTML statique : ils doivent figurer tels quels dans dist/index.html.
import { readFileSync } from "node:fs";
import process from "node:process";
import { URL } from "node:url";

const DIST_INDEX = new URL("../dist/index.html", import.meta.url);

/** Texte exact imposé par la constitution (P8). */
const DISCLAIMER =
  "Outil expérimental et éducatif. Ceci n'est pas un conseil en investissement.";
const TITLE = "Hello TradingHelper";

/** Texte visible approximatif : commentaires, scripts et balises retirés, espaces normalisés. */
function visibleText(html) {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&#39;|&apos;/g, "'")
    .replace(/\s+/g, " ");
}

function main() {
  let html;
  try {
    html = readFileSync(DIST_INDEX, "utf8");
  } catch {
    process.stderr.write("check-dist: dist/index.html introuvable, lancer `npm run build` d'abord.\n");
    return 1;
  }
  const text = visibleText(html);
  const failures = [];
  if (!text.includes(TITLE)) failures.push(`titre "${TITLE}" absent`);
  if (!text.includes(DISCLAIMER)) failures.push(`bandeau P8 absent : "${DISCLAIMER}"`);

  if (failures.length > 0) {
    for (const failure of failures) process.stderr.write(`check-dist: ${failure}\n`);
    return 1;
  }
  process.stdout.write("check-dist: OK (titre et bandeau P8 présents)\n");
  return 0;
}

process.exitCode = main();
