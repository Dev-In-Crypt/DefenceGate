/**
 * WP-160: contracts ending soon. The words of a contract period (where its end comes from, always said), the list's filters, its
 * paid part and its CSV. Shapes: GET /v1/tenders/ending and /v1/account/contracts/ending (backend dgate/expiring.py). No imports
 * beyond relative type ones: lib/wp160.check.ts compiles it on its own.
 */
import type { Cell } from './csv';
import type { ContractPeriod, Tender } from './types';

export const WITHIN = [3, 6, 12] as const;
export type Within = (typeof WITHIN)[number];
export const FULL_PAGE_SIZE = 50;
export const CSV_ROWS = 2000;
export const WHY = 'When a contract ends, the buyer usually tenders again: these are the contracts whose period, as the notice states it, ends soon.';

export const BASIS_LABEL: Record<NonNullable<ContractPeriod['endBasis']>, string> = {
  stated: 'stated end date',
  computed: 'computed from start + duration',
  estimated: 'estimated: award notice publication date + duration',
};

const UNIT: Record<NonNullable<ContractPeriod['durationUnit']>, [string, string]> = {
  DAY: ['day', 'days'], WEEK: ['week', 'weeks'], MONTH: ['month', 'months'], YEAR: ['year', 'years'],
};

export function durationText(p: Pick<ContractPeriod, 'duration' | 'durationUnit'>): string | null {
  if (!p.duration || !p.durationUnit) return null;
  const [one, many] = UNIT[p.durationUnit];
  return `${p.duration} ${p.duration === 1 ? one : many}`;
}

/** Where the end comes from, in words; for a period without an end, why there is none. */
export function basisText(p: ContractPeriod): string {
  if (p.end && p.endBasis) return BASIS_LABEL[p.endBasis];
  return p.duration ? 'duration only, no start: no end date' : 'no end date stated';
}

export function renewalText(p: Pick<ContractPeriod, 'renewal' | 'renewalsMax'>): string | null {
  if (!p.renewal) return null;
  const n = p.renewalsMax;
  return n ? `renewal options: up to ${n} renewal${n === 1 ? '' : 's'}` : 'renewal possible';
}

const day = (iso: string) => {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
};

/** "1 Apr 2026 – 31 Mar 2027" (a missing side is "?"); null when the notice states neither date and no end is derived. */
export function spanText(p: ContractPeriod): string | null {
  if (!p.start && !p.end) return null;
  return `${p.start ? day(p.start) : '?'} – ${p.end ? day(p.end) : '?'}`;
}

/** The one line a row or a page shows: span, duration, where the end comes from, renewal. */
export function periodLine(p: ContractPeriod): string {
  const parts = [spanText(p), durationText(p), basisText(p), renewalText(p)].filter((x): x is string => Boolean(x));
  return parts.join(' · ');
}

export interface EndingCoverage { country: string; dated: number; estimated: number }
export type EndingItem = Tender & { contractPeriod: ContractPeriod };
export interface EndingAnswer {
  within: Within; from: string; to: string; estimated: boolean;
  items: EndingItem[]; total: number; offset: number; freeRows: number; public: boolean;
  coverage: EndingCoverage[];
  page?: number; pageSize?: number;
  /** the account may download the CSV (Team and Consultant, or anyone while no plan is on sale) */
  csv?: boolean;
}

export interface EndingFilters { within: Within; country: string; cpv: string; buyer: string; estimated: boolean; page: number }

type SP = Record<string, string | string[] | undefined>;
const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? '';

export function parseEndingFilters(sp: SP): EndingFilters {
  const w = Number(first(sp.within));
  const within = (WITHIN as readonly number[]).includes(w) ? (w as Within) : 12;
  const country = first(sp.country).replace(/[^\p{L}\p{M}\s,.'’&-]/gu, '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const cpv = first(sp.cpv).replace(/[^0-9,]/g, '').slice(0, 40);
  const buyer = /^[0-9]{1,18}$/.test(first(sp.buyer)) ? first(sp.buyer) : '';
  const n = Number(first(sp.page));
  const page = Number.isFinite(n) && n >= 1 ? Math.min(Math.floor(n), 1000) : 1;
  return { within, country, cpv, buyer, estimated: first(sp.estimated) === 'true', page };
}

/** The API's query of the filters (no page); `country` as the API takes it (codes). */
export function endingQuery(f: Omit<EndingFilters, 'page'>): string {
  const p = new URLSearchParams();
  if (f.within !== 12) p.set('within', String(f.within));
  if (f.country) p.set('country', f.country);
  if (f.cpv) p.set('cpv', f.cpv);
  if (f.buyer) p.set('buyer', f.buyer);
  if (f.estimated) p.set('estimated', 'true');
  return p.toString();
}

export function endingHref(f: EndingFilters, over: Partial<EndingFilters> = {}, path = '/tenders/ending'): string {
  const g = { ...f, ...over };
  const p = new URLSearchParams(endingQuery(g));
  if (g.page > 1) p.set('page', String(g.page));
  return `${path}${p.size ? `?${p.toString()}` : ''}`;
}

/** What the visitor gets beyond the first rows: `signin`, `plan` (signed in, the plan has not the full list), `full`. */
export type EndingState = 'signin' | 'plan' | 'full';
export function endingState(accountStatus: number): EndingState {
  if (accountStatus === 200) return 'full';
  return accountStatus === 402 ? 'plan' : 'signin';
}

/** "Contract periods are read from notices of Germany (9,613), France (1,423) ..." from the API's coverage, never a fixed list. */
export function coverageLine(c: EndingCoverage[], name: (code: string) => string): string {
  const dated = c.filter((x) => x.dated > 0);
  if (dated.length === 0) return 'No notice we hold states a contract period we can date yet.';
  const list = dated.map((x) => `${name(x.country)} (${x.dated.toLocaleString('en-GB')})`).join(', ');
  const est = c.reduce((n, x) => n + x.estimated, 0);
  return `Contract periods we can date come from notices of ${list}. Other countries' notices state none we hold yet.`
    + (est === 1 ? ' 1 more award notice states only a duration: its end is an estimate, shown only when you ask for estimates.'
      : est ? ` ${est.toLocaleString('en-GB')} more award notices state only a duration: their end is an estimate, shown only when you ask for estimates.` : '');
}

export const ENDING_CSV_HEADER = ['title', 'buyer', 'buyer_country', 'cpv', 'contract_start', 'contract_end', 'end_basis', 'duration',
  'renewal', 'winners', 'notice_id', 'notice_url', 'our_page'];

export function endingCsvRows(items: EndingItem[], site: string): Cell[][] {
  return items.map((t) => {
    const p = t.contractPeriod;
    return [t.title, t.buyerName, t.country, t.cpv, p.start, p.end, p.end && p.endBasis ? BASIS_LABEL[p.endBasis] : basisText(p),
      durationText(p), renewalText(p), (t.awardedTo ?? []).map((w) => w.name).join(' | '), t.noticeId, t.source.url, `${site}/tenders/${t.slug}`];
  });
}
