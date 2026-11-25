/** Variation signée avec flèche ▲/▼ : jamais la couleur seule (spec F09 — R8, R12). */
import { changeParts } from "../lib/format";

export function Change({ value }: { value: number | null }) {
  const parts = changeParts(value);
  return (
    <span class="change" data-direction={parts.direction}>
      {parts.arrow === "" ? parts.text : `${parts.arrow} ${parts.text}`}
    </span>
  );
}
