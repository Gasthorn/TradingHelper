/** Page d'accueil (spec F09 — R4, R12). Tableau des symboles : T15. */
import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { Loading } from "../components/Loading";
import { useFile } from "../data/useData";
import type { ManifestFile } from "../types/export_manifest";
import type { OverviewFile } from "../types/export_overview";

export function Overview({ manifest }: { manifest: ManifestFile }) {
  if (manifest.data_as_of === null) {
    return (
      <section>
        <h1>Vue d'ensemble</h1>
        <EmptyState>Aucune donnée disponible.</EmptyState>
      </section>
    );
  }
  return <OverviewContent manifest={manifest} />;
}

function OverviewContent({ manifest }: { manifest: ManifestFile }) {
  const overview = useFile<OverviewFile>(manifest, "overview.json");
  return (
    <section>
      <h1>Vue d'ensemble</h1>
      {overview.status === "loading" && <Loading />}
      {overview.status === "error" && <ErrorPanel error={overview.error} />}
    </section>
  );
}
