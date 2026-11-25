/** Coque du dashboard : en-tête, manifest, aiguillage des routes (spec F09 — R1, R3). */
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ErrorPanel } from "./components/ErrorPanel";
import { Header } from "./components/Header";
import { Loading } from "./components/Loading";
import { useManifest } from "./data/useData";
import { useRoute } from "./hooks/useRoute";
import { useTheme } from "./hooks/useTheme";
import type { Route } from "./lib/routes";
import { NotFound } from "./pages/NotFound";
import { Overview } from "./pages/Overview";
import { Ticker } from "./pages/Ticker";
import type { ManifestFile } from "./types/export_manifest";

function Page({ route, manifest }: { route: Route; manifest: ManifestFile }) {
  switch (route.page) {
    case "overview":
      return <Overview manifest={manifest} />;
    case "ticker":
      return <Ticker key={route.symbol} symbol={route.symbol} />;
    case "not_found":
      return <NotFound />;
  }
}

export function App() {
  const route = useRoute();
  const manifest = useManifest();
  const theme = useTheme();
  // La page introuvable ne dépend d'aucune donnée.
  const key = route.page === "ticker" ? `ticker/${route.symbol}` : route.page;
  return (
    <>
      <Header
        dataAsOf={manifest.status === "ok" ? manifest.data.data_as_of : undefined}
        themePreference={theme.preference}
        onCycleTheme={theme.cycle}
      />
      <main>
        {route.page === "not_found" ? (
          <NotFound />
        ) : manifest.status === "loading" ? (
          <Loading />
        ) : manifest.status === "error" ? (
          <ErrorPanel error={manifest.error} />
        ) : (
          <ErrorBoundary key={key}>
            <Page route={route} manifest={manifest.data} />
          </ErrorBoundary>
        )}
      </main>
    </>
  );
}
