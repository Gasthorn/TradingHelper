/** Coque du dashboard : en-tête et aiguillage des routes (spec F09 — R1). */
import { Header } from "./components/Header";
import { useRoute } from "./hooks/useRoute";
import { NotFound } from "./pages/NotFound";
import { Overview } from "./pages/Overview";
import { Ticker } from "./pages/Ticker";

export function App() {
  const route = useRoute();
  return (
    <>
      <Header />
      <main>
        {route.page === "overview" && <Overview />}
        {route.page === "ticker" && <Ticker key={route.symbol} symbol={route.symbol} />}
        {route.page === "not_found" && <NotFound />}
      </main>
    </>
  );
}
