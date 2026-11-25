/**
 * Page d'accueil (spec F09 — R4, R12, R13). Ne charge que `manifest.json` et `overview.json`
 * (R2). Les sections M3 (indicateurs, classement, signaux) sont présentes et vides en M1.
 */
import type { ComponentChildren } from "preact";

import { Change } from "../components/Change";
import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { Loading } from "../components/Loading";
import { ScrollTable } from "../components/ScrollTable";
import { Sparkline } from "../components/Sparkline";
import { useFile } from "../data/useData";
import { formatPrice } from "../lib/format";
import { tickerHash } from "../lib/routes";
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
    <>
      <h1>Vue d'ensemble</h1>
      {overview.status === "loading" && <Loading />}
      {overview.status === "error" && <ErrorPanel error={overview.error} />}
      {overview.status === "ok" && (
        <>
          <TickersTable manifest={manifest} overview={overview.data} />
          <StrategySections overview={overview.data} />
        </>
      )}
    </>
  );
}

function TickersTable({ manifest, overview }: { manifest: ManifestFile; overview: OverviewFile }) {
  const bySymbol = new Map(overview.tickers.map((t) => [t.symbol, t]));
  const rows = manifest.tickers.flatMap((ticker) => {
    const data = bySymbol.get(ticker.symbol);
    return data === undefined ? [] : [{ ticker, data }];
  });
  return (
    <section aria-labelledby="tickers-title">
      <h2 id="tickers-title">Cours</h2>
      <ScrollTable label="Tableau des cours">
        <table class="data-table" aria-labelledby="tickers-title">
          <thead>
            <tr>
              <th scope="col">Symbole</th>
              <th scope="col">Nom</th>
              <th scope="col" class="num">
                Clôture
              </th>
              <th scope="col" class="num">
                Variation 1 j
              </th>
              <th scope="col">60 séances</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ ticker, data }) => (
              <tr key={ticker.symbol}>
                <th scope="row">
                  <a href={tickerHash(ticker.symbol)}>{ticker.symbol}</a>
                </th>
                <td>
                  {ticker.name}
                  {ticker.benchmark && <span class="tag">indice de référence</span>}
                </td>
                <td class="num">{formatPrice(data.last_close)}</td>
                <td class="num">
                  <Change value={data.change_1d} />
                </td>
                <td>
                  <Sparkline values={data.spark} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollTable>
    </section>
  );
}

/** Sections dépendant des stratégies (R13, M3) : état vide tant qu'aucune stratégie n'est suivie. */
function StrategySections({ overview }: { overview: OverviewFile }) {
  return (
    <>
      <Section id="kpis" title="Indicateurs clés">
        {overview.kpis.best_strategy_30d === null && overview.leaderboard.length === 0 && (
          <EmptyState>Aucune stratégie suivie pour l'instant.</EmptyState>
        )}
      </Section>
      <Section id="leaderboard" title="Classement des stratégies">
        {overview.leaderboard.length === 0 && <EmptyState>Aucune stratégie suivie pour l'instant.</EmptyState>}
      </Section>
      <Section id="signals" title="Derniers signaux">
        {overview.latest_signals.length === 0 && <EmptyState>Aucun signal pour l'instant.</EmptyState>}
      </Section>
    </>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ComponentChildren }) {
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{title}</h2>
      {children}
    </section>
  );
}
