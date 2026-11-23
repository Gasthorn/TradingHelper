/** Composant racine du dashboard. Les pages (Overview, Ticker…) arrivent avec F09. */
export function App() {
  // Erreur volontaire : chaîne affectée à un number (PR de test R15, ne pas merger).
  const count: number = "0";
  return <p class="placeholder">Dashboard en construction ({count}).</p>;
}
