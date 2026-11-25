/**
 * Fiche d'un symbole (spec F09 — R14, R16, R17, R18). Le graphique (`lightweight-charts`,
 * chargé dynamiquement) arrive en T17–T19 ; ici : résolution du symbole, chargement de
 * `tickers/{SYMBOL}.json`, sélecteurs de période, d'indicateurs et de stratégie, fiche
 * « Signal du jour » (vide en M1).
 */
import { useState } from "preact/hooks";

import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { Loading } from "../components/Loading";
import { useFile } from "../data/useData";
import { PERIODS, type Period } from "../lib/dates";
import { strategyOptions } from "../lib/markers";
import type { ManifestFile, ManifestTicker } from "../types/export_manifest";
import type { TickerFile } from "../types/export_ticker";

export interface Overlays {
  sma20: boolean;
  sma50: boolean;
  sma200: boolean;
  bollinger: boolean;
}

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
            <OverlaySelector value={overlays} onChange={setOverlays} />
            <StrategySelector options={strategyOptions(file.data.markers)} value={strategy} onChange={setStrategy} />
          </div>
          <div class="price-chart" data-testid="price-chart" />
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

function OverlaySelector({ value, onChange }: { value: Overlays; onChange: (o: Overlays) => void }) {
  return (
    <fieldset class="overlays">
      <legend class="control-label">Indicateurs</legend>
      {(Object.keys(OVERLAY_LABELS) as (keyof Overlays)[]).map((key) => (
        <label key={key} class="check">
          <input
            type="checkbox"
            checked={value[key]}
            onChange={(event) => {
              onChange({ ...value, [key]: event.currentTarget.checked });
            }}
          />
          {OVERLAY_LABELS[key]}
        </label>
      ))}
    </fieldset>
  );
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
