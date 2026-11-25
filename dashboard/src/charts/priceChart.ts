/**
 * Graphique de prix de la fiche ticker (spec F09 — R8, R15, R16, R17). Seul module qui importe
 * `lightweight-charts` ; chargé par `import()` dynamique depuis `pages/Ticker.tsx` pour rester
 * hors du bundle initial (R2, R26).
 *
 * - panneau 0 : chandeliers (haussiers creux, baissiers pleins), volume sur une échelle à part,
 *   overlays SMA20/50/200 et Bollinger ;
 * - panneau 1 : RSI14 avec les lignes 30 et 70.
 *
 * Les valeurs exportées sont tracées telles quelles ; les `null` de warm-up sont omis.
 * Le graphique suit le thème (R7) : il observe `data-theme` sur <html> et relit les couleurs
 * des variables CSS, sans être recréé.
 * L'état tracé est exposé en attributs `data-*` du conteneur pour les tests e2e (le canvas
 * n'est pas lisible), décision 3 du plan.
 */
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  LineSeries,
  LineStyle,
  type SeriesMarker,
  type Time,
  createChart,
  createSeriesMarkers,
} from "lightweight-charts";

import type { MarkerView } from "../lib/markers";

import { type BarWindow, linePoints } from "../lib/series";
import type { TickerSeries } from "../types/export_ticker";

export interface Overlays {
  sma20: boolean;
  sma50: boolean;
  sma200: boolean;
  bollinger: boolean;
}

export interface PriceChart {
  setData(series: TickerSeries, window: BarWindow): void;
  setOverlays(overlays: Overlays): void;
  /** Marqueurs BUY ▲ sous la bougie, SELL ▼ au-dessus, avec leur libellé (R8, R17). */
  setMarkers(markers: readonly MarkerView[]): void;
  /** Détruit le graphique et cesse d'observer le thème. */
  destroy(): void;
}

const OVERLAY_ORDER: (keyof Overlays)[] = ["sma20", "sma50", "sma200", "bollinger"];
const RSI_LINES = [30, 70] as const;

interface Palette {
  bg: string;
  fg: string;
  grid: string;
  up: string;
  down: string;
  volume: string;
  sma20: string;
  sma50: string;
  sma200: string;
  bollinger: string;
  rsi: string;
}

/** Couleurs lues dans les variables CSS du thème courant (style.css). */
function readPalette(): Palette {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return {
    bg: v("--bg", "#ffffff"),
    fg: v("--fg", "#1a1a1a"),
    grid: v("--grid", "#e5e7eb"),
    up: v("--up", "#0a6b37"),
    down: v("--down", "#b3261e"),
    volume: v("--volume", "#9ca3af"),
    sma20: v("--sma20", "#1d4ed8"),
    sma50: v("--sma50", "#b45309"),
    sma200: v("--sma200", "#7c3aed"),
    bollinger: v("--bollinger", "#6b7280"),
    rsi: v("--rsi", "#0e7490"),
  };
}

let nextChartId = 1;

export function createPriceChart(container: HTMLElement, initial: Overlays): PriceChart {
  let palette = readPalette();
  const chart: IChartApi = createChart(container, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: palette.bg },
      textColor: palette.fg,
      attributionLogo: true, // attribution TradingView (licence Apache-2.0, NOTICE)
    },
    grid: { vertLines: { color: palette.grid }, horzLines: { color: palette.grid } },
    timeScale: { borderVisible: false },
    rightPriceScale: { borderVisible: false },
  });

  const candles = chart.addSeries(CandlestickSeries, {
    upColor: "rgba(0, 0, 0, 0)", // creuse : la forme distingue la hausse, pas seulement la couleur (R8)
    borderUpColor: palette.up,
    wickUpColor: palette.up,
    downColor: palette.down,
    borderDownColor: palette.down,
    wickDownColor: palette.down,
  });
  const volume = chart.addSeries(HistogramSeries, {
    priceScaleId: "volume",
    priceFormat: { type: "volume" },
    color: palette.volume,
    lastValueVisible: false,
    priceLineVisible: false,
  });
  chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

  const line = (color: string, style: LineStyle = LineStyle.Solid) =>
    chart.addSeries(LineSeries, {
      color,
      lineWidth: 1,
      lineStyle: style,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });
  const overlaySeries: Record<keyof Overlays, ISeriesApi<"Line">[]> = {
    sma20: [line(palette.sma20)],
    sma50: [line(palette.sma50)],
    sma200: [line(palette.sma200)],
    bollinger: [line(palette.bollinger, LineStyle.Dashed), line(palette.bollinger, LineStyle.Dashed)],
  };

  const rsi = chart.addSeries(LineSeries, { color: palette.rsi, lineWidth: 1, priceLineVisible: false }, 1);
  const rsiLines = RSI_LINES.map((level) =>
    rsi.createPriceLine({ price: level, color: palette.fg, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "" }),
  );
  chart.panes()[1]?.setStretchFactor(0.3);

  const markerLayer = createSeriesMarkers(candles, []);
  container.dataset.markers = "0";

  let overlays = initial;
  let lastData: { series: TickerSeries; window: BarWindow } | null = null;
  let lastMarkers: readonly MarkerView[] = [];

  /** Volume coloré comme la bougie du jour (dépend de la palette). */
  function renderVolume(): void {
    if (lastData === null) return;
    const { series, window } = lastData;
    const data = [];
    for (let i = Math.max(0, window.from); i <= window.to; i++) {
      const [time, open, close, value] = [series.date[i], series.open[i], series.close[i], series.volume[i]];
      if (time === undefined || open === undefined || close === undefined || value === undefined) continue;
      data.push({ time, value, color: close >= open ? palette.up : palette.down });
    }
    volume.setData(data);
  }

  function renderMarkers(): void {
    const items: SeriesMarker<Time>[] = lastMarkers.map((m) =>
      m.action === "BUY"
        ? { time: m.date, position: "belowBar", shape: "arrowUp", color: palette.up, text: "BUY" }
        : { time: m.date, position: "aboveBar", shape: "arrowDown", color: palette.down, text: "SELL" },
    );
    markerLayer.setMarkers(items);
    container.dataset.markers = String(items.length);
  }

  /** Relit les couleurs du thème courant et les applique à toutes les séries. */
  function applyTheme(): void {
    palette = readPalette();
    chart.applyOptions({
      layout: { background: { type: ColorType.Solid, color: palette.bg }, textColor: palette.fg },
      grid: { vertLines: { color: palette.grid }, horzLines: { color: palette.grid } },
    });
    candles.applyOptions({
      borderUpColor: palette.up,
      wickUpColor: palette.up,
      downColor: palette.down,
      borderDownColor: palette.down,
      wickDownColor: palette.down,
    });
    for (const key of OVERLAY_ORDER) {
      for (const s of overlaySeries[key]) s.applyOptions({ color: palette[key] });
    }
    rsi.applyOptions({ color: palette.rsi });
    for (const lineApi of rsiLines) lineApi.applyOptions({ color: palette.fg });
    renderVolume();
    renderMarkers();
    container.dataset.theme = document.documentElement.dataset.theme ?? "light";
  }

  const themeObserver = new MutationObserver(applyTheme);
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  container.dataset.theme = document.documentElement.dataset.theme ?? "light";
  container.dataset.chartId = String(nextChartId++);
  let available: Record<keyof Overlays, boolean> = { sma20: true, sma50: true, sma200: true, bollinger: true };

  function applyOverlays(): void {
    const shown = OVERLAY_ORDER.filter((key) => overlays[key] && available[key]);
    for (const key of OVERLAY_ORDER) {
      for (const s of overlaySeries[key]) s.applyOptions({ visible: shown.includes(key) });
    }
    container.dataset.overlays = shown.join(",");
  }

  container.dataset.upStyle = "hollow";
  container.dataset.downStyle = "filled";
  container.dataset.panes = String(chart.panes().length);
  container.dataset.rsiLines = RSI_LINES.join(",");

  return {
    setData(series, window) {
      const dates = series.date;
      const from = Math.max(0, window.from);
      const candleData = [];
      for (let i = from; i <= window.to; i++) {
        const [time, open, high, low, close] = [dates[i], series.open[i], series.high[i], series.low[i], series.close[i]];
        if (time === undefined || open === undefined || high === undefined || low === undefined || close === undefined) continue;
        candleData.push({ time, open, high, low, close });
      }
      candles.setData(candleData);
      lastData = { series, window };
      renderVolume();
      const [sma20] = overlaySeries.sma20;
      const [sma50] = overlaySeries.sma50;
      const [sma200] = overlaySeries.sma200;
      const [bbUpper, bbLower] = overlaySeries.bollinger;
      sma20?.setData(linePoints(dates, series.sma20, window));
      sma50?.setData(linePoints(dates, series.sma50, window));
      sma200?.setData(linePoints(dates, series.sma200, window));
      bbUpper?.setData(linePoints(dates, series.bb_upper, window));
      bbLower?.setData(linePoints(dates, series.bb_lower, window));
      rsi.setData(linePoints(dates, series.rsi14, window));
      chart.timeScale().fitContent();

      available = {
        sma20: series.sma20.some((v) => v !== null),
        sma50: series.sma50.some((v) => v !== null),
        sma200: series.sma200.some((v) => v !== null),
        bollinger: series.bb_upper.some((v) => v !== null),
      };
      applyOverlays();
      container.dataset.bars = String(candleData.length);
      container.dataset.firstDate = candleData[0]?.time ?? "";
      container.dataset.lastDate = candleData.at(-1)?.time ?? "";
    },

    setOverlays(next) {
      overlays = next;
      applyOverlays();
    },

    setMarkers(markers) {
      lastMarkers = markers;
      renderMarkers();
    },

    destroy() {
      themeObserver.disconnect();
      chart.remove();
    },
  };
}
