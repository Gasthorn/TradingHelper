/**
 * Limite d'erreur par page (plan F09, « Risques ») : un fichier conforme à sa version mais mal
 * formé ne doit pas laisser un écran blanc ; la page affiche `ErrorPanel` à la place.
 */
import { Component, type ComponentChildren } from "preact";

import { ErrorPanel } from "./ErrorPanel";

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<{ children: ComponentChildren }, State> {
  override state: State = { error: null };

  static override getDerivedStateFromError(error: unknown): State {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  override render() {
    return this.state.error === null ? this.props.children : <ErrorPanel error={this.state.error} />;
  }
}
