/**
 * Conteneur de tableau à défilement horizontal propre (spec F09 — R9) : la page ne défile
 * jamais horizontalement. Focusable au clavier pour faire défiler le tableau (axe :
 * `scrollable-region-focusable`).
 */
import type { ComponentChildren } from "preact";

export function ScrollTable({ label, children }: { label: string; children: ComponentChildren }) {
  return (
    <div class="scroll-table" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}
