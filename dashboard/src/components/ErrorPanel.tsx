/** Message d'erreur de données nommant le fichier en cause (spec F09 — R3). */
import { DataError } from "../data/loader";

export function ErrorPanel({ error }: { error: Error }) {
  const detail = error instanceof DataError ? error.message : `Erreur d'affichage : ${error.message}`;
  return (
    <div class="error-panel" role="alert">
      <p class="error-panel__title">Impossible d'afficher cette page.</p>
      <p>{detail}</p>
    </div>
  );
}
