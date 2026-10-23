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

/** `ok-incremental` (WP-87): finished, on time, with no minimum to compare it with (Met expected minimum: Not measured). */
export type FreshnessKind = 'ok' | 'ok-incremental' | 'partial' | 'failed' | 'never' | 'stale' | 'one-off';

export interface Freshness {
  kind: FreshnessKind;
  /** "Stale: last ran 5 days ago", "One-off load, last run 3 Oct 2026"; null when there is nothing to add. */
  note: string | null;
}

/**
 * What the API says about a source's rhythm (`/v1/sources`, 19 October 2026): how often it is collected, after how many
 * hours a run is late for that, and whether it is (`stale`: null when the source has no rhythm, undefined on an older API).
 */
export interface SourceRhythm { updateFreq?: string | null; staleAfterHours?: number | null; stale?: boolean | null }

export function sourceFreshness(
  s: { id: string; status: 'ok' | 'partial' | 'failed' | 'never'; lastRunAt: string | null; coverage?: number | null; records?: number } & SourceRhythm,
  ref: Date,
): Freshness {
  if (s.lastRunAt === null || s.status === 'never') return { kind: 'never', note: null };
  const last = new Date(s.lastRunAt);
  if (Number.isNaN(last.getTime())) return { kind: s.status, note: null };
  if (ONE_OFF_SOURCES.includes(s.id) || (s.updateFreq ?? '').trim().toLowerCase() === 'one-off') {
    const day = `${last.getUTCDate()} ${MONTHS[last.getUTCMonth()]} ${last.getUTCFullYear()}`;
    return { kind: s.status === 'ok' ? 'one-off' : s.status, note: `One-off load, last run ${day}` };
  }
  const age = ref.getTime() - last.getTime();
  const days = Math.floor(age / DAY_MS);
  // The API says whether a run is late for the source's own rhythm: a monthly source is not stale after three days
  // (CORDIS and EDF were, UX audit T16). Only an API that does not send `stale` falls back to the daily rule.
  const late = s.stale !== undefined ? s.stale === true : age > STALE_AFTER_DAYS * DAY_MS;
  if (late) return { kind: s.status === 'ok' ? 'stale' : s.status, note: `Stale: last ran ${days} days ago` };
  const monthly = (s.updateFreq ?? '').trim().toLowerCase() === 'monthly';
  const note = monthly && age > STALE_AFTER_DAYS * DAY_MS ? `Collected monthly, last ran ${days} days ago` : null;
  // WP-87: an OK run with no minimum to meet ("Not measured") is not plain OK: SEDIA's run of 1 record read only what changed
  if (s.status === 'ok' && s.coverage === null) {
    const what = typeof s.records === 'number' ? `it fetched ${s.records.toLocaleString('en-GB')} ${s.records === 1 ? 'record' : 'records'}, ` : '';
    return { kind: 'ok-incremental', note: [note, `No minimum is set for this source, so the run is not measured against one: ${what}reading only what changed since the run before.`].filter(Boolean).join('. ') };
  }
  return { kind: s.status, note };
}

/**
 * Why a run that is not `ok` is not, in the API's own fixed sentence (`statusReason`, T18): a run can be Partial with
 * "Met expected minimum: Yes" because it was cut short for another reason. null for a run that is ok or has no reason.
 */
export function statusReasonLine(s: { status: string; statusReason?: string | null }): string | null {
  const reason = (s.statusReason ?? '').trim();
  if (!reason || s.status === 'ok' || s.status === 'never') return null;
  return `${s.status === 'failed' ? 'Why the last run failed' : 'Why the last run is partial'}: ${reason}${/[.!?]$/.test(reason) ? '' : '.'}`;
}

/**
 * When a run counts as late, in the API's words: "a daily source after 3 days, a monthly one after 40 days". null when
 * the API sends no rhythm (an older build): the page then keeps the daily rule.
 */
export function lateRuleSentence(sources: { updateFreq?: string | null; staleAfterHours?: number | null }[]): string | null {
  const by = new Map<string, number>();
  for (const s of sources) {
    const f = (s.updateFreq ?? '').trim().toLowerCase();
    if (f && typeof s.staleAfterHours === 'number' && s.staleAfterHours > 0) by.set(f, Math.round(s.staleAfterHours / 24));
  }
  const parts = [...by.entries()].sort((a, b) => a[1] - b[1]).map(([f, d]) => `a ${f} source after ${d} ${d === 1 ? 'day' : 'days'}`);
  return parts.length > 0 ? parts.join(', ') : null;
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

/**
 * WP-87: "Latest run of a source of this list: 22 Oct 2026, 07:29 UTC (TED)". One definition (the newest successful or partial run
 * of the sources that feed the list), and the source named, so it is not read as the footer's run of any source.
 */
export function updatedLine(iso: string, source: string | null | undefined): string {
  return `Latest run of its sources: ${formatStamp(iso)}${source ? ` (${source})` : ''}`;
}

const formatStamp = (iso: string) => {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
};

/** The "Met expected minimum" cell: a run is compared with the minimum we set for that source, not with the source. */
/**
 * WP-88: a source by a name a reader knows: PLACSP as the Spanish platform it is, the EU portal without its internal code (SEDIA).
 * The attribution line keeps the source's own wording.
 */
export function sourceDisplay(name: string): string {
  const n = (name ?? '').trim();
  if (n === 'PLACSP') return 'Plataforma de Contratación (Spain)';
  const m = /^PLACSP \((.+)\)$/.exec(n);
  if (m) return m[1];
  return n.replace(/\s*\(SEDIA\)$/, '');
}

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
  const median = s.monthlyMedian ?? 0;
  // WP-96: the API's median is over the last 12 whole months (it was every month since the first, "about 21" for PLACSP's 41,142)
  const usual = median >= 10 ? ` In the last 12 months the usual month held about ${median.toLocaleString('en-GB')} notices.`
    : median > 0 ? ' The usual month holds only a handful of notices, so month-by-month gaps say little.' : '';
  // A source with only a handful of notices a month has no meaningful "half of the usual month".
  if (median > 0 && median < 10) return `${s.name}: publication dates ${span}.${usual}`;
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

/**
 * The page a person reads for a source, where the address the API holds is its data interface (an API root answers
 * 404, 400 or 405 to a browser: three of the 14 "Open ..." links of /data, 16 October 2026). Only the sources whose
 * stored address is not a page are listed here; any other keeps the address it has.
 */
const SOURCE_HOME: Record<string, string> = {
  ted: 'https://ted.europa.eu/en/',
  fr_boamp: 'https://www.boamp.fr/',
  nl_tenderned: 'https://www.tenderned.nl/',
  pl_ezam: 'https://ezamowienia.gov.pl/',
  de_bkms: 'https://www.oeffentlichevergabe.de/',
  se_vinnova: 'https://www.vinnova.se/en/',
};
export function sourcePage(id: string, stored: string | null | undefined): string | null {
  return SOURCE_HOME[id] ?? stored ?? null;
}

/**
 * What to say under an empty estimated value, per source id. A source whose connector never reads a value
 * (`valueRead` false: eZamowienia, TenderNed) says so, whatever the count: the buyer may well have stated one.
 * Any other source gets the share, in whole percent, of its held notices with no usable value (a placeholder amount
 * counts as none), only with at least 20 notices and a count from the API. That share mixes three causes (the notice
 * states none, a placeholder, or a kind of amount we do not read), so it does not say the buyer stated nothing.
 */
export function valueMissingNotes(
  sources: { id: string; heldCount?: number | null; valueStatedCount?: number | null; valueRead?: boolean | null }[],
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const s of sources) {
    if (s.valueRead === false) {
      out[s.id] = 'Not collected from this source: we do not read estimated values from its notices yet.';
      continue;
    }
    if (typeof s.heldCount !== 'number' || typeof s.valueStatedCount !== 'number' || s.heldCount < 20) continue;
    const pct = Math.min(100, Math.max(0, Math.round((1 - s.valueStatedCount / s.heldCount) * 100)));
    out[s.id] = `No usable estimated value in ${pct} % of notices from this source.`;
  }
  return out;
}

/** What "no usable value" counts, said on the notice's own page under the note (a card has no room for it). */
export const VALUE_MISSING_MEANS = 'That counts a notice that states none, one that states a placeholder such as 0 or 1, and one that states a kind of amount we do not read yet (a framework maximum, the values of lot awards).';

/** The note for one source, or null when there is none to give. */
export function valueMissingNote(notes: Record<string, string>, sourceId: string | null | undefined): string | null {
  return (sourceId ? notes[sourceId] : undefined) ?? null;
}

/** "Showing the last answer received at 12 Oct 2026, 09:14 UTC: the data service is slow right now." */
export function staleNote(asOf: string | null | undefined, formatter: (iso: string) => string): string | null {
  return asOf ? `The data service did not answer in time. This is its last answer, as of ${formatter(asOf)}; reload in a minute for the current one.` : null;
}
