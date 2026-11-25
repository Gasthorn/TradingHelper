/** « Page introuvable » : route inconnue ou non livrée (spec F09 — R1). */
export function NotFound() {
  return (
    <section>
      <h1>Page introuvable</h1>
      <p>Cette page n'existe pas ou n'est pas encore disponible.</p>
      <p>
        <a class="action-link" href="#/">
          Retour à l'accueil
        </a>
      </p>
    </section>
  );
}
