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

/**
 * The data time of a list (`meta.updatedAt`), or null when the API does not send it or it is not a date. Callers
 * hide the "data updated" line on null: the render time of a page is never shown as the time of the data.
 */
export function listUpdatedAt(page: { meta?: unknown } | null | undefined): string | null {
  const meta = page?.meta;
  if (typeof meta !== 'object' || meta === null) return null;
  const t = (meta as { updatedAt?: unknown }).updatedAt;
  return typeof t === 'string' && t !== '' && !Number.isNaN(new Date(t).getTime()) ? t : null;
}

/** The "Met expected minimum" cell: a run is compared with the minimum we set for that source, not with the source. */
export function minimumMet(coverage: number | null): string {
  if (coverage === null) return 'Not measured';
  if (coverage >= 1) return 'Yes';
  return `No: ${Math.min(99, Math.floor(coverage * 100))}% of the minimum`;
}

/**
 * Months (`YYYY-MM`, any order) as ranges a person reads: ["2026-05","2026-06","2026-07","2026-12"] becomes
 * ["May to Jul 2026", "Dec 2026"]. Anything that is not a month is dropped.
 */
export function monthRanges(months: readonly string[]): string[] {
  const keys = [...new Set(months.filter((m) => /^\d{4}-(0[1-9]|1[0-2])$/.test(m)))].sort();
  const out: string[] = [];
  const index = (k: string) => Number(k.slice(0, 4)) * 12 + Number(k.slice(5, 7)) - 1;
  const say = (k: string, withYear: boolean) => `${MONTHS[Number(k.slice(5, 7)) - 1]}${withYear ? ` ${k.slice(0, 4)}` : ''}`;
  for (let i = 0; i < keys.length;) {
    let j = i;
    while (j + 1 < keys.length && index(keys[j + 1]) === index(keys[j]) + 1) j += 1;
    const from = keys[i];
    const to = keys[j];
    if (i === j) out.push(say(from, true));
    else out.push(from.slice(0, 4) === to.slice(0, 4) ? `${say(from, false)} to ${say(to, true)}` : `${say(from, true)} to ${say(to, true)}`);
    i = j + 1;
  }
  return out;
}

/**
 * What /data says about the holes of one tender source, worked out from the counts the API sends and not written
 * by hand (site-qa2:N6: a hand-written list said Poland's May to August 2026 were not held when 951 to 1,253
 * notices a month are). null when the API did not send the figures.
 */
export function gapSentence(s: { name: string; heldFrom?: string | null; heldTo?: string | null; monthlyMedian?: number | null; gapMonths?: string[] | null }): string | null {
  const span = heldSpan(s.heldFrom, s.heldTo);
  if (!span || s.gapMonths === undefined || s.gapMonths === null) return null;
  const usual = s.monthlyMedian ? ` The usual month holds about ${s.monthlyMedian.toLocaleString('en-GB')} notices.` : '';
  if (s.gapMonths.length === 0) return `${s.name}: publication dates ${span}.${usual} No whole month between the first and the last is below half of that.`;
  return `${s.name}: publication dates ${span}.${usual} Months with fewer than half of that: ${monthRanges(s.gapMonths).join(', ')}.`;
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
