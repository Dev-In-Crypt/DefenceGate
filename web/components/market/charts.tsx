import { barLayout, percentText, shareOf } from '@/lib/market';
import { formatNumber } from '@/lib/format';
import { DataTable } from '@/components/dg/data-table';

/**
 * Plain SVG bar chart of counts of notices. No chart library: the drawing carries no text, so it scales
 * with its box on any screen, and every figure is also in a table under it. The table is the accessible
 * form of the chart (the SVG is a labelled image), and it is open by default for short series.
 */
export interface ChartBar {
  label: string;
  primary: number;
  /** Stacked on `primary`. */
  secondary?: number;
  /** The period is not over: drawn lighter, and said so. */
  partial?: boolean;
}

const W = 720;
const H = 200;

export function BarChart({ id, title, summary, bars, primaryName, secondaryName, labelHeader, unit = 'notices' }: {
  id: string;
  title: string;
  /** One sentence for a reader who cannot see the drawing. */
  summary: string;
  bars: ChartBar[];
  primaryName: string;
  secondaryName?: string;
  labelHeader: string;
  unit?: string;
}) {
  const totals = bars.map((b) => b.primary + (b.secondary ?? 0));
  const { max, bars: boxes, scale } = barLayout(totals, W, H);
  const tallest = totals.reduce((best, v, i) => (v > totals[best] ? i : best), 0);
  const stacked = secondaryName !== undefined;
  const first = bars[0]?.label;
  const last = bars.length > 1 ? bars[bars.length - 1].label : null;
  return (
    <figure className="m-0 flex flex-col gap-3">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-labelledby={`${id}-title ${id}-desc`}
        className="h-40 w-full rounded-md bg-surface-inset sm:h-52">
        <title id={`${id}-title`}>{title}</title>
        <desc id={`${id}-desc`}>{summary}</desc>
        {[1, 2, 3].map((k) => (
          <line key={k} x1={0} x2={W} y1={(H * k) / 4} y2={(H * k) / 4} stroke="var(--line)" strokeWidth={1}
            vectorEffect="non-scaling-stroke" />
        ))}
        {bars.map((b, i) => {
          const box = boxes[i];
          const low = scale(b.primary);
          const high = scale(b.secondary ?? 0);
          return (
            <g key={b.label} opacity={b.partial ? 0.45 : 1} shapeRendering="crispEdges">
              {b.primary > 0 && <rect x={box.x} y={H - low} width={box.w} height={low} fill="var(--primary)" />}
              {(b.secondary ?? 0) > 0 && <rect x={box.x} y={H - low - high} width={box.w} height={high} fill="var(--link)" />}
            </g>
          );
        })}
      </svg>
      <div className="flex justify-between gap-2 font-mono text-mono text-ink-muted" aria-hidden="true">
        <span>{first}</span>
        {last && <span>{last}</span>}
      </div>
      <figcaption className="flex flex-col gap-1 text-small text-ink-muted">
        <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="size-3 rounded-pill bg-primary" />{primaryName}</span>
          {stacked && <span className="inline-flex items-center gap-2"><span aria-hidden="true" className="size-3 rounded-pill bg-link" />{secondaryName}</span>}
          <span>Scale: 0 to {formatNumber(max)} {unit}. Tallest bar: {formatNumber(totals[tallest] ?? 0)} ({bars[tallest]?.label}).</span>
        </span>
        {bars.some((b) => b.partial) && <span>The lighter bar is a period that is not over yet.</span>}
      </figcaption>
      <details open={bars.length <= 12} className="border-t border-line">
        <summary className="inline-flex min-h-11 cursor-pointer items-center text-small font-semibold">Figures as a table</summary>
        <div className="max-h-80 overflow-y-auto">
          <DataTable label={title} minWidth={320}>
            <thead>
              <tr>
                <th scope="col">{labelHeader}</th>
                <th scope="col" className="text-right">{primaryName}</th>
                {stacked && <th scope="col" className="text-right">{secondaryName}</th>}
                {stacked && <th scope="col" className="text-right">All</th>}
              </tr>
            </thead>
            <tbody>
              {bars.map((b) => (
                <tr key={b.label}>
                  <th scope="row">{b.label}{b.partial ? ' (not complete)' : ''}</th>
                  <td className="text-right font-mono tabular-nums">{formatNumber(b.primary)}</td>
                  {stacked && <td className="text-right font-mono tabular-nums">{formatNumber(b.secondary ?? 0)}</td>}
                  {stacked && <td className="text-right font-mono tabular-nums">{formatNumber(b.primary + (b.secondary ?? 0))}</td>}
                </tr>
              ))}
            </tbody>
          </DataTable>
        </div>
      </details>
    </figure>
  );
}

export interface RankRow { key: string; label: React.ReactNode; count: number }

/**
 * A ranking as a table whose last column is a bar: the numbers are text in the table, the bar repeats them
 * for the eye and is hidden from assistive technology. `total` adds each row's share of it.
 */
export function RankTable({ caption, labelHeader, rows, total, unit = 'Notices' }: {
  caption: string; labelHeader: string; rows: RankRow[]; total?: number; unit?: string;
}) {
  const top = Math.max(1, ...rows.map((r) => r.count));
  return (
    // The bar column is for the eye only (the numbers are in the table), so below sm it is dropped and the table fits a phone.
    <DataTable label={caption} minWidth={280}>
      <thead>
        <tr>
          <th scope="col">{labelHeader}</th>
          <th scope="col" className="text-right">{unit}</th>
          {total !== undefined && <th scope="col" className="text-right">Share</th>}
          <th scope="col" className="hidden w-1/3 sm:table-cell"><span className="sr-only">Bar</span></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key}>
            <th scope="row">{r.label}</th>
            <td className="text-right font-mono tabular-nums">{formatNumber(r.count)}</td>
            {total !== undefined && <td className="text-right font-mono tabular-nums">{percentText(shareOf(r.count, total))}</td>}
            <td aria-hidden="true" className="hidden sm:table-cell">
              <div className="h-3 rounded-pill bg-primary" style={{ width: `${Math.max(1, (r.count / top) * 100)}%` }} />
            </td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}
