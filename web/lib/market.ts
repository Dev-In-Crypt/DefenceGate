/**
 * Pure helpers for the market overview and the buyer profile: the figures are counts of notices
 * published, drawn as bars. Import-free so lib/ui.check.ts can run it on its own.
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;

/** "2026-10" -> "Oct 2026". Anything that is not a year-month is returned as it came. */
export function monthLabel(ym: string): string {
  const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(ym);
  return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1]}` : ym;
}

/** The smallest 1, 2 or 5 times a power of ten that is at least `n`; 1 for zero or less. */
export function niceMax(n: number): number {
  if (!(n > 0)) return 1;
  const power = 10 ** Math.floor(Math.log10(n));
  for (const step of [1, 2, 5, 10]) if (step * power >= n) return step * power;
  return 10 * power;
}

/**
 * A share as a percentage a reader can compare: one decimal below 10%, none above, and "Under 0.1%"
 * for a share that is not zero but would round to it. null is "not measured", never 0%.
 */
export function percentText(share: number | null): string {
  if (share === null || !Number.isFinite(share)) return 'Not measured';
  if (share <= 0) return '0%';
  const pct = share * 100;
  if (pct < 0.05) return 'Under 0.1%';
  return pct < 10 ? `${pct.toFixed(1)}%` : `${Math.round(pct)}%`;
}

export interface BarBox { x: number; y: number; w: number; h: number }

/**
 * Where each bar goes in a `width` x `height` box. The top of the box is `max`, the data's largest
 * total rounded up to a round number. `scale` turns a count into a height, so a second value can be
 * stacked on a first (TED, and the national sources above it).
 */
export function barLayout(
  totals: number[], width: number, height: number, gap = 2,
): { max: number; bars: BarBox[]; scale: (v: number) => number } {
  const max = niceMax(Math.max(0, ...totals));
  const n = Math.max(1, totals.length);
  const w = Math.max(1, (width - gap * (n - 1)) / n);
  const scale = (v: number) => (Math.max(0, v) / max) * height;
  const bars = totals.map((v, i) => {
    const h = scale(v);
    return { x: i * (w + gap), y: height - h, w, h };
  });
  return { max, bars, scale };
}

/** The share of `part` in `whole` as 0..1; 0 when there is no whole. */
export function shareOf(part: number, whole: number): number {
  return whole > 0 ? Math.min(1, Math.max(0, part / whole)) : 0;
}

/** "21 days", "1 day"; "Not measured" when nothing states a deadline. */
export function daysText(days: number | null): string {
  if (days === null) return 'Not measured';
  return `${days} ${days === 1 ? 'day' : 'days'}`;
}

/** WP-87: the bars of a buyer's notices per year: the years shown, with "Earlier" before them and "No date" after when they hold
 * notices, so the bars add up to `tenderCount` (BAAINBw: 4,324 over the years against 3,335 in the archive). */
export function profileYearBars(p: { perYear: { year: number; count: number }[]; perYearEarlier?: number; perYearUndated?: number }): { label: string; primary: number; partial?: boolean }[] {
  const last = p.perYear[p.perYear.length - 1]?.year;
  const first = p.perYear[0]?.year;
  return [
    ...((p.perYearEarlier ?? 0) > 0 ? [{ label: first ? `Before ${first}` : 'Earlier', primary: p.perYearEarlier ?? 0 }] : []),
    ...p.perYear.map((y) => ({ label: String(y.year), primary: y.count, partial: y.year === last })),
    ...((p.perYearUndated ?? 0) > 0 ? [{ label: 'No date', primary: p.perYearUndated ?? 0 }] : []),
  ];
}

/** Six months of watching before an amendment share says anything about a buyer (WP-87; the archive began in September 2026). */
export const AMENDMENT_HISTORY_DAYS = 183;

/** Whether a buyer's amendment share is shown, and since when its notices were watched ("Sep 2026"). An API that does not say when
 * is read as the archive's start, September 2026. */
export function amendmentsShown(a: { observedFrom?: string | null }, asOf: string): { shown: boolean; since: string } {
  const from = a.observedFrom ? new Date(a.observedFrom) : new Date('2026-09-01T00:00:00Z');
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const since = `${months[from.getUTCMonth()]} ${from.getUTCFullYear()}`;
  return { shown: new Date(asOf).getTime() - from.getTime() >= AMENDMENT_HISTORY_DAYS * 86_400_000, since };
}
