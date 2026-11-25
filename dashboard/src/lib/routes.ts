/**
 * Routage par hash (spec F09 — R1, R14). Module pur : `parseHash(location.hash)`.
 * Les routes `[M3]` (portfolios, portfolio, models, health) ne sont pas livrées en M1 et
 * mènent à « Page introuvable ».
 */

export type Route =
  | { page: "overview" }
  | { page: "ticker"; symbol: string } // décodé, en majuscules
  | { page: "not_found" };

const NOT_FOUND: Route = { page: "not_found" };

function decodeSymbol(raw: string): string | null {
  try {
    const symbol = decodeURIComponent(raw).trim().toUpperCase();
    return symbol === "" ? null : symbol;
  } catch {
    return null; // encodage invalide (URIError)
  }
}

/** Route d'un hash (`""`, `"#/"`, `"#/ticker/AAPL"`…). Ne lève jamais d'exception. */
export function parseHash(hash: string): Route {
  const path = hash.startsWith("#") ? hash.slice(1) : hash;
  if (path !== "" && !path.startsWith("/")) return NOT_FOUND;
  const segments = path.split("/").filter((s) => s !== "");

  if (segments.length === 0) return { page: "overview" };
  if (segments.length === 2 && segments[0] === "ticker") {
    const symbol = decodeSymbol(segments[1] ?? "");
    return symbol === null ? NOT_FOUND : { page: "ticker", symbol };
  }
  return NOT_FOUND;
}

/** Hash de la fiche d'un symbole (lien depuis l'Overview). */
export function tickerHash(symbol: string): string {
  return `#/ticker/${encodeURIComponent(symbol)}`;
}
