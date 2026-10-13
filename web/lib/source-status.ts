/**
 * How a source's last run reads on /data once its age is taken into account. "OK" means the last run finished
 * and fetched at least the minimum we expect; it says nothing about how old that run is, so a run older than
 * STALE_AFTER_DAYS is shown as stale, and a one-off load (not meant to run again) as what it is.
 * Pure and import-free so lib/ui.check.ts can run it on its own.
 */
export const STALE_AFTER_DAYS = 3;
/** Loads made once on purpose. A later run is not expected, so age is not a fault. */
export const ONE_OFF_SOURCES: readonly string[] = ['pl_atlas'];

const DAY_MS = 86_400_000;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;

export type FreshnessKind = 'ok' | 'partial' | 'failed' | 'never' | 'stale' | 'one-off';

export interface Freshness {
  kind: FreshnessKind;
  /** "Stale: last ran 5 days ago", "One-off load, last run 3 Oct 2026"; null when there is nothing to add. */
  note: string | null;
}

export function sourceFreshness(
  s: { id: string; status: 'ok' | 'partial' | 'failed' | 'never'; lastRunAt: string | null },
  ref: Date,
): Freshness {
  if (s.lastRunAt === null || s.status === 'never') return { kind: 'never', note: null };
  const last = new Date(s.lastRunAt);
  if (Number.isNaN(last.getTime())) return { kind: s.status, note: null };
  if (ONE_OFF_SOURCES.includes(s.id)) {
    const day = `${last.getUTCDate()} ${MONTHS[last.getUTCMonth()]} ${last.getUTCFullYear()}`;
    return { kind: s.status === 'ok' ? 'one-off' : s.status, note: `One-off load, last run ${day}` };
  }
  const age = ref.getTime() - last.getTime();
  if (age > STALE_AFTER_DAYS * DAY_MS) {
    const days = Math.floor(age / DAY_MS);
    return { kind: s.status === 'ok' ? 'stale' : s.status, note: `Stale: last ran ${days} days ago` };
  }
  return { kind: s.status, note: null };
}

/** The "Met expected minimum" cell: a run is compared with the minimum we set for that source, not with the source. */
export function minimumMet(coverage: number | null): string {
  if (coverage === null) return 'Not measured';
  if (coverage >= 1) return 'Yes';
  return `No: ${Math.min(99, Math.floor(coverage * 100))}% of the minimum`;
}

/**
 * "3 Nov 2020 to 12 Oct 2026": the span of publication dates we hold for a source, so that a gap (a bulletin
 * that starts in 2020) is visible. Dates arrive as YYYY-MM-DD. null when the source gives no publication date.
 */
export function heldSpan(from: string | null | undefined, to: string | null | undefined): string | null {
  const say = (iso: string | null | undefined): string | null => {
    const m = iso ? /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) : null;
    if (!m || Number(m[2]) < 1 || Number(m[2]) > 12) return null;
    return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
  };
  const a = say(from);
  const b = say(to);
  if (a && b) return a === b ? a : `${a} to ${b}`;
  return a ?? b;
}
