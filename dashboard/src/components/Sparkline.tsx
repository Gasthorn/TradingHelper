/**
 * Sparkline en SVG inline, sans bibliothèque (spec F09 — R12, décision Q7) : une polyligne
 * normalisée entre le minimum et le maximum des clôtures.
 */
import { formatPrice } from "../lib/format";

const WIDTH = 100;
const HEIGHT = 28;
const PAD = 2;

export function Sparkline({ values }: { values: readonly number[] }) {
  const last = values.at(-1) ?? null;
  const label = `Clôtures des ${String(values.length)} dernières séances, dernière à ${formatPrice(last)}`;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => (values.length === 1 ? WIDTH / 2 : PAD + (i * (WIDTH - 2 * PAD)) / (values.length - 1));
  const y = (v: number) => (max === min ? HEIGHT / 2 : HEIGHT - PAD - ((v - min) * (HEIGHT - 2 * PAD)) / span);
  const points = values.map((v, i) => `${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(" ");
  return (
    <svg class="sparkline" viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`} width={WIDTH} height={HEIGHT} role="img" aria-label={label}>
      {values.length > 1 ? (
        <polyline points={points} fill="none" stroke="currentColor" stroke-width="1.5" vector-effect="non-scaling-stroke" />
      ) : (
        last !== null && <circle cx={x(0)} cy={y(last)} r="2" fill="currentColor" />
      )}
    </svg>
  );
}
