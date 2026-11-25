/** État vide explicite d'une section (spec F09 — R4). */
import type { ComponentChildren } from "preact";

export function EmptyState({ children }: { children: ComponentChildren }) {
  return <p class="empty-state">{children}</p>;
}
