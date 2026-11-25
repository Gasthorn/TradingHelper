/**
 * Fiche d'un symbole (spec F09 — R14–R18) : résolution du symbole, chargement de
 * `tickers/{SYMBOL}.json`, sélecteurs de période, d'indicateurs et de stratégie, graphique
 * (`charts/priceChart.ts`, chargé par `import()` dynamique : hors du bundle initial, R2),
 * fiche « Signal du jour » (vide en M1).
 */
import { useEffect, useRef, useState } from "preact/hooks";

import type { Overlays, PriceChart } from "../charts/priceChart";

import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { Loading } from "../components/Loading";
import { useFile } from "../data/useData";
import { PERIODS, type Period } from "../lib/dates";
import { formatConfidence, formatDate, formatDecimal } from "../lib/format";
import { type MarkerView, strategyOptions, visibleMarkers } from "../lib/markers";
import { isAllNull, periodWindow } from "../lib/series";
import type { ManifestFile, ManifestStrategy, ManifestTicker } from "../types/export_manifest";
import type { ExportMarker, TickerFile, TickerSeries } from "../types/export_ticker";

/** Premier affichage (décision Q10). */
export const DEFAULT_OVERLAYS: Overlays = { sma20: true, sma50: true, sma200: false, bollinger: false };
export const DEFAULT_PERIOD: Period = "6M";

const OVERLAY_LABELS: Record<keyof Overlays, string> = {
  sma20: "SMA20",
  sma50: "SMA50",
  sma200: "SMA200",
  bollinger: "Bollinger",
};

export function Ticker({ manifest, symbol }: { manifest: ManifestFile; symbol: string }) {
  const ticker = manifest.tickers.find((t) => t.symbol.toUpperCase() === symbol);
  if (ticker === undefined) {
    return (
      <section>
        <h1>{symbol}</h1>
        <EmptyState>Pas de données pour {symbol}</EmptyState>
      </section>
    );
  }
  return <TickerContent manifest={manifest} ticker={ticker} />;
}

function TickerContent({ manifest, ticker }: { manifest: ManifestFile; ticker: ManifestTicker }) {
  const file = useFile<TickerFile>(manifest, `tickers/${ticker.symbol}.json`);
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);
  const [overlays, setOverlays] = useState<Overlays>(DEFAULT_OVERLAYS);
  const [strategy, setStrategy] = useState<string | null>(null);

  return (
    <>
      <h1>{ticker.symbol}</h1>
      <p class="subtitle">
        {ticker.name}
        {ticker.benchmark && <span class="tag">indice de référence</span>}
      </p>
      {file.status === "loading" && <Loading />}
      {file.status === "error" && <ErrorPanel error={file.error} />}
      {file.status === "ok" && (
        <>
          <div class="chart-controls">
            <PeriodSelector value={period} onChange={setPeriod} />
            <OverlaySelector value={overlays} unavailable={unavailableOverlays(file.data.series)} onChange={setOverlays} />
            <StrategySelector options={strategyOptions(file.data.markers)} value={strategy} onChange={setStrategy} />
          </div>
          <ChartWithMarkers
            series={file.data.series}
            markers={file.data.markers}
            strategies={manifest.strategies}
            period={period}
            overlays={overlays}
            strategy={strategy}
          />
        </>
      )}
      <section aria-labelledby="signal-title">
        <h2 id="signal-title">Signal du jour</h2>
        <EmptyState>Aucun signal pour l'instant.</EmptyState>
      </section>
    </>
  );
}

function PeriodSelector({ value, onChange }: { value: Period; onChange: (p: Period) => void }) {
  return (
    <div class="segmented" role="radiogroup" aria-labelledby="period-label">
      <span id="period-label" class="control-label">
        Période
      </span>
      {PERIODS.map((p) => (
        <label key={p} class="segmented__item">
          <input
            type="radio"
            name="period"
            value={p}
            checked={p === value}
            onChange={() => {
              onChange(p);
            }}
          />
          {p}
        </label>
      ))}
    </div>
  );
}

/** Indicateurs sans aucune valeur (ex. SMA200 sur moins de 200 barres) : non sélectionnables (R15). */
function unavailableOverlays(series: TickerSeries): Set<keyof Overlays> {
  const out = new Set<keyof Overlays>();
  if (isAllNull(series.sma20)) out.add("sma20");
  if (isAllNull(series.sma50)) out.add("sma50");
  if (isAllNull(series.sma200)) out.add("sma200");
  if (isAllNull(series.bb_upper)) out.add("bollinger");
  return out;
}

function OverlaySelector({
  value,
  unavailable,
  onChange,
}: {
  value: Overlays;
  unavailable: ReadonlySet<keyof Overlays>;
  onChange: (o: Overlays) => void;
}) {
  return (
    <fieldset class="overlays">
      <legend class="control-label">Indicateurs</legend>
      {(Object.keys(OVERLAY_LABELS) as (keyof Overlays)[]).map((key) => {
        const disabled = unavailable.has(key);
        return (
          <label key={key} class={disabled ? "check check--disabled" : "check"}>
            <input
              type="checkbox"
              checked={value[key] && !disabled}
              disabled={disabled}
              onChange={(event) => {
                onChange({ ...value, [key]: event.currentTarget.checked });
              }}
            />
            {OVERLAY_LABELS[key]}
            {disabled && <span class="hint"> (historique insuffisant)</span>}
          </label>
        );
      })}
    </fieldset>
  );
}

/** Graphique et légende des marqueurs visibles (période et stratégie choisies). */
function ChartWithMarkers({
  series,
  markers,
  strategies,
  period,
  overlays,
  strategy,
}: {
  series: TickerSeries;
  markers: readonly ExportMarker[];
  strategies: readonly ManifestStrategy[];
  period: Period;
  overlays: Overlays;
  strategy: string | null;
}) {
  const range = periodWindow(series.date, period);
  const dates = new Set(series.date.slice(range.from, range.to + 1));
  const visible = visibleMarkers(markers, strategy, dates, strategies);
  return (
    <>
      <PriceChartView series={series} period={period} overlays={overlays} markers={visible} />
      <MarkerLegend markers={visible} />
    </>
  );
}

/** Détail de chaque marqueur affiché : confiance, modèle et performance (P8). */
function MarkerLegend({ markers }: { markers: readonly MarkerView[] }) {
  if (markers.length === 0) return null;
  return (
    <ul class="marker-legend" aria-label="Signaux affichés">
      {markers.map((m) => (
        <li key={`${m.date}-${m.strategy_id}`} data-action={m.action}>
          <strong class="marker-legend__action">{m.action === "BUY" ? "▲ BUY" : "▼ SELL"}</strong> · {formatDate(m.date)} ·{" "}
          {m.strategy_id} · confiance {formatConfidence(m.confidence)} · modèle {m.modelId ?? "—"} · Sharpe OOS{" "}
          {formatDecimal(m.sharpeOos)}
        </li>
      ))}
    </ul>
  );
}

/** Conteneur du graphique : création après chargement du module, puis mises à jour. */
function PriceChartView({
  series,
  period,
  overlays,
  markers,
}: {
  series: TickerSeries;
  period: Period;
  overlays: Overlays;
  markers: readonly MarkerView[];
}) {
  const host = useRef<HTMLDivElement>(null);
  const [chart, setChart] = useState<PriceChart | null>(null);
  const initialOverlays = useRef(overlays);

  useEffect(() => {
    let disposed = false;
    let created: PriceChart | null = null;
    void import("../charts/priceChart").then(({ createPriceChart }) => {
      if (disposed || host.current === null) return;
      created = createPriceChart(host.current, initialOverlays.current);
      setChart(created);
    });
    return () => {
      disposed = true;
      created?.destroy();
    };
  }, []);

  useEffect(() => {
    chart?.setData(series, periodWindow(series.date, period));
  }, [chart, series, period]);

  useEffect(() => {
    chart?.setOverlays(overlays);
  }, [chart, overlays]);

  useEffect(() => {
    chart?.setMarkers(markers);
  }, [chart, markers]);

  return <div ref={host} class="price-chart" data-testid="price-chart" />;
}

/** Masqué sans marqueur (R4) ; « Toutes » = aucune restriction. */
function StrategySelector({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string | null;
  onChange: (s: string | null) => void;
}) {
  if (options.length === 0) return null;
  return (
    <label class="strategy">
      <span class="control-label">Stratégie</span>
      <select
        value={value ?? ""}
        onChange={(event) => {
          onChange(event.currentTarget.value === "" ? null : event.currentTarget.value);
        }}
      >
        <option value="">Toutes</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}
