/** Fiche d'un symbole (spec F09 — R14–R18). Contenu : T16–T19. */
export function Ticker({ symbol }: { symbol: string }) {
  return (
    <section>
      <h1>{symbol}</h1>
    </section>
  );
}
