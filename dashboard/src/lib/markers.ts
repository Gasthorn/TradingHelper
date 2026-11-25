/**
 * Marqueurs de signaux de la fiche ticker (spec F09 — R17, P8). Module pur.
 * Chaque marqueur affiché porte le modèle et la performance de sa stratégie, lus dans
 * `manifest.strategies` (F08 R16).
 */
import type { ManifestStrategy } from "../types/export_manifest";
import type { ExportMarker } from "../types/export_ticker";

/** Marqueur prêt à afficher : confiance + modèle + performance (P8). */
export interface MarkerView extends ExportMarker {
  modelId: string | null;
  sharpeOos: number | null;
  /** Faux si la stratégie est absente de `manifest.strategies` (affichage « — »). */
  known: boolean;
}

/** Options du sélecteur de stratégie : identifiants présents, uniques, triés. */
export function strategyOptions(markers: readonly ExportMarker[]): string[] {
  return [...new Set(markers.map((m) => m.strategy_id))].sort();
}

/**
 * Marqueurs à tracer : filtrés par stratégie (`null` = toutes), limités aux dates présentes
 * dans la série (un marqueur hors série est ignoré sans erreur), enrichis pour P8.
 * L'ordre d'entrée (date puis stratégie, F08 R9) est conservé.
 */
export function visibleMarkers(
  markers: readonly ExportMarker[],
  strategy: string | null,
  dates: ReadonlySet<string>,
  strategies: readonly ManifestStrategy[],
): MarkerView[] {
  const byId = new Map(strategies.map((s) => [s.id, s]));
  return markers
    .filter((m) => (strategy === null || m.strategy_id === strategy) && dates.has(m.date))
    .map((m) => {
      const s = byId.get(m.strategy_id);
      return {
        ...m,
        modelId: s?.model_id ?? null,
        sharpeOos: s?.sharpe_oos ?? null,
        known: s !== undefined,
      };
    });
}
