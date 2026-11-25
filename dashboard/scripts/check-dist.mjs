// Vérifie le build du dashboard (spec F00 — R12, R13, R14 ; F09 R5) : `npm run build && npm run check:dist`.
// Le titre et le bandeau P8 sont en HTML statique : ils doivent figurer tels quels dans dist/index.html.
// Si TH_DASHBOARD_BASE est défini (ex. /TradingHelper/), les assets locaux doivent en porter le préfixe.
import { readFileSync } from "node:fs";
import process from "node:process";
import { URL } from "node:url";

const DIST_INDEX = new URL("../dist/index.html", import.meta.url);

/** Texte exact imposé par la constitution (P8). */
const DISCLAIMER =
  "Outil expérimental et éducatif. Ceci n'est pas un conseil en investissement.";
/** Titre exact de la page (`<title>`), F00 R12 modifiée par F09 (décision 1 du plan). */
const TITLE = "TradingHelper";

/** Texte visible approximatif : commentaires, scripts et balises retirés, espaces normalisés. */
function visibleText(html) {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&#39;|&apos;/g, "'")
    .replace(/\s+/g, " ");
}

/** URLs d'assets locaux référencés par src="…" ou href="…" (liens externes, data: et ancres exclus). */
function localAssetUrls(html) {
  const urls = [];
  for (const match of html.matchAll(/\s(?:src|href)="([^"]+)"/g)) {
    const url = match[1];
    if (!/^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i.test(url)) urls.push(url);
  }
  return urls;
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
  const title = /<title>([^<]*)<\/title>/.exec(html)?.[1]?.trim();
  if (title !== TITLE) failures.push(`titre "${title ?? ""}" au lieu de "${TITLE}"`);
  if (!text.includes(DISCLAIMER)) failures.push(`bandeau P8 absent : "${DISCLAIMER}"`);

  const base = process.env.TH_DASHBOARD_BASE || "/";
  const assets = localAssetUrls(html);
  if (assets.length === 0) failures.push("aucun asset local référencé dans dist/index.html");
  for (const url of assets) {
    if (!url.startsWith(base)) failures.push(`asset "${url}" sans le préfixe base "${base}"`);
  }

  if (failures.length > 0) {
    for (const failure of failures) process.stderr.write(`check-dist: ${failure}\n`);
    return 1;
  }
  process.stdout.write(
    `check-dist: OK (titre et bandeau P8 présents, ${assets.length} assets sous "${base}")\n`,
  );
  return 0;
}

process.exitCode = main();
