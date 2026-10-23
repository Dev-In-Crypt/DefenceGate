/**
 * The weekly digest (/digest, /digest/[YYYY-Www], /digest.atom): week helpers, the URL filter, one-line headlines and
 * the Atom document. Pure and import-light: lib/digest.check.ts runs it on its own.
 *
 * An issue is one ISO week, Monday 00:00 to the next Monday, UTC. The API builds it from the same data as the change
 * list and the funding list; this file only words it. Titles, buyers, funders, countries, dates and the eligibility
 * line, as everywhere else: no contact data.
 */
import { rfc3339, tagId, xmlText } from './atom';
import type { Digest, DigestCall, DigestTender } from './types';
import type { SearchParams } from './filters';
import { BUYER_COUNTRIES } from './taxonomy';

export const WEEK_RE = /^(\d{4})-W(\d{2})$/;

/** A week id the API could know: the shape, and a week number that exists. The API settles the rest (404). */
export function isWeek(v: string): boolean {
  const m = WEEK_RE.exec(v);
  if (!m) return false;
  const w = Number(m[2]);
  return w >= 1 && w <= 53;
}

/** The Monday of an ISO week, as a UTC date. */
export function weekMonday(week: string): Date {
  const m = WEEK_RE.exec(week);
  if (!m) throw new Error(`not a week: ${week}`);
  const jan4 = new Date(Date.UTC(Number(m[1]), 0, 4));
  const monday = new Date(jan4.getTime() - ((jan4.getUTCDay() + 6) % 7) * 86_400_000);
  return new Date(monday.getTime() + (Number(m[2]) - 1) * 7 * 86_400_000);
}

/** WP-90: the ISO week a moment falls in, UTC ("2026-W43"): the week under way, whose changes so far /changes lists. */
export function weekOf(d: Date): string {
  const day = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  // the ISO year is the Thursday's
  const thursday = new Date(day.getTime() + (3 - ((day.getUTCDay() + 6) % 7)) * 86_400_000);
  const week = 1 + Math.floor((thursday.getTime() - weekMonday(`${thursday.getUTCFullYear()}-W01`).getTime()) / (7 * 86_400_000));
  return `${thursday.getUTCFullYear()}-W${String(week).padStart(2, '0')}`;
}

/** "This week so far: 19 to 23 October" (to the day of `ref`, UTC). */
export function weekSoFarLabel(week: string, ref: Date): string {
  const start = weekMonday(week);
  const from = start.getUTCMonth() === ref.getUTCMonth() ? `${start.getUTCDate()}` : `${start.getUTCDate()} ${MONTHS[start.getUTCMonth()]}`;
  return `This week so far: ${from} to ${ref.getUTCDate()} ${MONTHS[ref.getUTCMonth()]} ${ref.getUTCFullYear()}`;
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** "Week 41: 5 to 11 October 2026" (the last day is the Sunday; the issue ends at the next Monday 00:00 UTC). */
export function weekLabel(week: string): string {
  const start = weekMonday(week);
  const end = new Date(start.getTime() + 6 * 86_400_000);
  const num = Number(WEEK_RE.exec(week)![2]);
  const sameMonth = start.getUTCMonth() === end.getUTCMonth();
  const from = sameMonth ? `${start.getUTCDate()}` : `${start.getUTCDate()} ${MONTHS[start.getUTCMonth()]}`;
  return `Week ${num}: ${from} to ${end.getUTCDate()} ${MONTHS[end.getUTCMonth()]} ${end.getUTCFullYear()}`;
}

export interface DigestFilters { country?: string }

/** The countries an issue can be narrowed to: a buyer country of a notice, or `EU` for the Commission's own calls. */
export const DIGEST_COUNTRIES: Record<string, string> = { ...BUYER_COUNTRIES, EU: 'European Union (EU programmes)' };

/** `country` is one code of DIGEST_COUNTRIES; anything else is dropped (the page then shows every country). */
export function parseDigestFilters(sp: SearchParams): DigestFilters {
  const raw = Array.isArray(sp.country) ? sp.country[0] : sp.country;
  const code = (raw ?? '').trim().toUpperCase();
  return Object.hasOwn(DIGEST_COUNTRIES, code) ? { country: code } : {};
}

/** A `country` that was asked for and is not one of DIGEST_COUNTRIES: the page says it was ignored, the feed refuses it. */
export function unknownDigestCountry(sp: SearchParams): string | null {
  const raw = (Array.isArray(sp.country) ? sp.country[0] : sp.country) ?? '';
  const code = raw.trim().toUpperCase();
  return code && !Object.hasOwn(DIGEST_COUNTRIES, code) ? code.slice(0, 8) : null;
}

export function digestQuery(f: DigestFilters): string {
  return f.country ? `?country=${f.country}` : '';
}

export function digestPath(week: string | null, f: DigestFilters = {}): string {
  return `${week ? `/digest/${week}` : '/digest'}${digestQuery(f)}`;
}

/** The sections of an issue, in the order they are shown, with the heading's words and the list they come from. */
export const SECTIONS = [
  { id: 'funding-new', title: 'New funding calls', count: 'callsNew', list: 'callsNew' },
  { id: 'funding-opened', title: 'Calls that opened', count: 'callsOpened', list: 'callsOpened' },
  { id: 'funding-moved', title: 'Funding calls with a date moved', count: 'callsAmended', list: 'callsAmended' },
  { id: 'funding-closing', title: 'Calls closing in the next 14 days', count: 'callsClosing', list: 'callsClosing' },
  { id: 'cascade', title: 'Calls with cascade funding', count: 'cascade', list: 'cascadeCalls' },
  { id: 'tenders-new', title: 'New defence notices', count: 'tendersNew', list: 'tendersNew' },
  { id: 'tenders-amended', title: 'Amended notices', count: 'tendersAmended', list: 'tendersAmended' },
] as const;

/** Of a section: shown fewer than counted. */
export function truncation(shown: number, counted: number): string | null {
  return counted > shown ? `Showing the first ${shown} of ${counted}.` : null;
}

/** How many notices a list of rows stands for: a row with `repeats` stands for that many identical ones (the counts count every notice). */
export function noticesIn(rows: { repeats?: number }[]): number {
  return rows.reduce((n, r) => n + Math.max(1, Math.floor(r.repeats ?? 1)), 0);
}

/** "×13" for a row that stands for 13 identical notices; null for a single one. */
export function repeatsLabel(repeats: number | undefined): string | null {
  return repeats !== undefined && repeats > 1 ? `×${Math.floor(repeats)}` : null;
}

/**
 * Where a tender section's "has the rest" leads: the change list of that week and kind (`/changes?week=2026-W42&kind=new`,
 * API `/v1/changes?week=&kind=`), with the digest's country when it is a buyer country (`EU` is the Commission's own calls: no notice has it).
 */
export function restOfTendersHref(week: string, kind: 'new' | 'amended', country?: string): string {
  const q = new URLSearchParams({ week, kind });
  if (country && Object.hasOwn(BUYER_COUNTRIES, country)) q.set('country', country);
  return `/changes?${q.toString()}`;
}

export function totalItems(d: Digest): number {
  const c = d.counts;
  // The cascade calls are also in the lists above: they are not added twice.
  return c.tendersNew + c.tendersAmended + c.callsNew + c.callsAmended + c.callsOpened + c.callsClosing;
}

function callHeadline(c: DigestCall): string {
  const what = ({ 'call-new': 'New call', 'call-opened': 'Opened', 'call-amended': 'Date moved', 'call-closing': 'Closing' } as const)[c.kind];
  return `${what}: ${c.title}`;
}

/** At most `n` plain lines for a feed entry: the calls first, then the notices. */
export function headlines(d: Digest, n = 8): string[] {
  const calls = [...d.callsNew, ...d.callsOpened, ...d.callsAmended, ...d.callsClosing].map(callHeadline);
  const tenders = [...d.tendersNew, ...d.tendersAmended].map((t: DigestTender) => `${t.kind === 'new' ? 'New notice' : 'Amended notice'}: ${t.title}${repeatsLabel(t.repeats) ? ` (${repeatsLabel(t.repeats)})` : ''}`);
  return [...calls, ...tenders].slice(0, n);
}

/** One sentence of counts, for a page and a feed entry. */
export function countsSentence(d: Pick<Digest, 'counts'>): string {
  const c = d.counts;
  const part = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  return [
    part(c.callsNew, 'new funding call', 'new funding calls'), part(c.callsOpened, 'call opened', 'calls opened'),
    part(c.callsClosing, 'call closing within 14 days', 'calls closing within 14 days'),
    part(c.tendersNew, 'new defence notice', 'new defence notices'), part(c.tendersAmended, 'amended notice', 'amended notices'),
  ].join(', ') + (c.cascade > 0 ? `; ${c.cascade} with cascade funding` : '') + '.';
}

export interface DigestAtomOptions { origin: string; country?: string; generatedAt: string }

/**
 * The feed: one entry per issue (newest first), each with the counts and the first headlines. The entry's id is the
 * week, so a reader never shows an issue twice; `updated` is the end of the week the issue covers.
 */
export function buildDigestAtom(issues: Digest[], o: DigestAtomOptions): string {
  const q = o.country ? `?country=${o.country}` : '';
  const self = `${o.origin}/digest.atom${q}`;
  const updated = issues.reduce((m, d) => (d.weekTo > m ? d.weekTo : m), '') || o.generatedAt;
  const entries = issues.map((d) => {
    const text = [countsSentence(d), ...headlines(d, 10)].join('\n');
    return [
      '  <entry>',
      `    <id>${xmlText(tagId(o.origin, 'digest', d.week, o.country ?? 'all'))}</id>`,
      `    <title>${xmlText(`Weekly digest, ${weekLabel(d.week)}${o.country ? ` (${o.country})` : ''}`)}</title>`,
      `    <link rel="alternate" type="text/html" href="${xmlText(`${o.origin}${digestPath(d.week, { country: o.country })}`)}"/>`,
      `    <updated>${rfc3339(d.weekTo)}</updated>`,
      `    <summary type="text">${xmlText(text)}</summary>`,
      '  </entry>',
    ].join('\n');
  });
  return [
    '<?xml version="1.0" encoding="utf-8"?>',
    '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">',
    `  <id>${xmlText(tagId(o.origin, 'digest', o.country ?? 'all'))}</id>`,
    '  <title>DefenceGate: weekly digest</title>',
    `  <subtitle>${xmlText('Each week: new and amended defence notices, new, opened and closing funding calls, and calls with cascade funding. One entry per week.')}</subtitle>`,
    `  <updated>${rfc3339(updated)}</updated>`,
    `  <link rel="self" type="application/atom+xml" href="${xmlText(self)}"/>`,
    `  <link rel="alternate" type="text/html" href="${xmlText(`${o.origin}/digest${q}`)}"/>`,
    '  <author><name>DefenceGate</name></author>',
    ...entries,
    '</feed>',
    '',
  ].join('\n');
}

/** WP-87: a section's calls in two parts, the defence calls and the dual-use ones (shown under their own heading). */
export function splitByRegime<T extends { regime?: string | null }>(items: T[]): { defence: T[]; dualUse: T[] } {
  return { defence: items.filter((c) => c.regime !== 'dual-use'), dualUse: items.filter((c) => c.regime === 'dual-use') };
}
