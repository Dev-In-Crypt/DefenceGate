import type {
  BuyerFilters, BuyerSort, CallFilters, CallSort, CallStatusFilter, CountryCode, ListView, ProgrammeCode, Regime,
  TenderFilters, TenderScopeFilter, TenderSort, TenderStatusFilter,
} from './types';
import { BUYER_COUNTRY_CODES, COUNTRIES, PROGRAMME_CODES, REGIME_CODES } from './taxonomy';

/** Next.js page searchParams shape. */
export type SearchParams = Record<string, string | string[] | undefined>;

export const DEFAULT_PAGE_SIZE = 10;
export const DEFAULT_SORT: CallSort = 'deadline-asc';
export const DEFAULT_STATUS: CallStatusFilter = 'open';
/** Budget filter and budget sort refer to this currency unless the URL says otherwise. Nothing is converted. */
export const DEFAULT_CURRENCY = 'EUR';
/** Caps on what a visitor can put in the URL; they bound the request sent to the API. */
export const MAX_QUERY_LENGTH = 100;
export const MAX_PAGE = 1000;

/** URL keys — short and stable so shared links survive. */
export const PARAM = {
  q: 'q', programme: 'programme', regime: 'regime', country: 'country', status: 'status',
  from: 'from', to: 'to', min: 'min', max: 'max', currency: 'currency', sort: 'sort', page: 'page', view: 'view',
  scope: 'scope', hasOpen: 'hasOpen', cpv: 'cpv',
} as const;

const STATUSES: CallStatusFilter[] = ['open', 'forthcoming', 'closing-soon', 'closed', 'all'];
const SORTS: CallSort[] = ['deadline-asc', 'deadline-desc', 'budget-desc'];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const CURRENCY_RE = /^[A-Za-z]{3}$/;

/** A real calendar day written YYYY-MM-DD: "2026-02-31" and "2026-13-01" are not days, and the API refuses them. */
export function isDay(v: string): boolean {
  if (!DATE_RE.test(v)) return false;
  const d = new Date(`${v}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
}

function first(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}
function list<T extends string>(v: string | string[] | undefined, allowed: readonly T[]): T[] | undefined {
  if (!v) return undefined;
  const raw = (Array.isArray(v) ? v : [v]).flatMap((s) => s.split(','));
  const out = raw.map((s) => s.trim()).filter((s): s is T => (allowed as readonly string[]).includes(s));
  const unique = [...new Set(out)];
  return unique.length ? unique : undefined;
}
/** Trimmed and truncated to MAX_QUERY_LENGTH characters (code points, so a pair is never split). */
function searchText(v: string | undefined): string | undefined {
  if (!v) return undefined;
  const s = Array.from(v.trim().slice(0, MAX_QUERY_LENGTH * 2)).slice(0, MAX_QUERY_LENGTH).join('').trim();
  return s || undefined;
}
function num(v: string | undefined): number | undefined {
  if (!v) return undefined;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : undefined;
}
function oneOf<T extends string>(v: string | undefined, allowed: readonly T[]): T | undefined {
  return v && (allowed as readonly string[]).includes(v) ? (v as T) : undefined;
}

export function parseCallFilters(sp: SearchParams): CallFilters {
  const from = first(sp[PARAM.from]);
  const to = first(sp[PARAM.to]);
  const page = num(first(sp[PARAM.page]));
  const currency = first(sp[PARAM.currency]);
  return {
    q: searchText(first(sp[PARAM.q])),
    programme: list<ProgrammeCode>(sp[PARAM.programme], PROGRAMME_CODES),
    regime: list<Regime>(sp[PARAM.regime], REGIME_CODES),
    country: list<CountryCode>(sp[PARAM.country], Object.keys(COUNTRIES) as CountryCode[]),
    status: oneOf(first(sp[PARAM.status]), STATUSES) ?? DEFAULT_STATUS,
    deadlineFrom: from && isDay(from) ? from : undefined,
    deadlineTo: to && isDay(to) ? to : undefined,
    budgetMin: num(first(sp[PARAM.min])),
    budgetMax: num(first(sp[PARAM.max])),
    currency: currency && CURRENCY_RE.test(currency) ? currency.toUpperCase() : DEFAULT_CURRENCY,
    sort: oneOf(first(sp[PARAM.sort]), SORTS) ?? DEFAULT_SORT,
    page: page && page >= 1 ? Math.min(Math.floor(page), MAX_PAGE) : 1,
    pageSize: DEFAULT_PAGE_SIZE,
  };
}

export function parseView(sp: SearchParams): ListView {
  return first(sp[PARAM.view]) === 'calendar' ? 'calendar' : 'list';
}

/** Serialise back to a URL query, omitting defaults so URLs stay short. */
export function toQuery(f: CallFilters, extra: Partial<Record<string, string | undefined>> = {}): string {
  const p = new URLSearchParams();
  if (f.q) p.set(PARAM.q, f.q);
  if (f.programme?.length) p.set(PARAM.programme, f.programme.join(','));
  if (f.regime?.length) p.set(PARAM.regime, f.regime.join(','));
  if (f.country?.length) p.set(PARAM.country, f.country.join(','));
  if (f.status && f.status !== DEFAULT_STATUS) p.set(PARAM.status, f.status);
  if (f.deadlineFrom) p.set(PARAM.from, f.deadlineFrom);
  if (f.deadlineTo) p.set(PARAM.to, f.deadlineTo);
  if (f.budgetMin !== undefined) p.set(PARAM.min, String(f.budgetMin));
  if (f.budgetMax !== undefined) p.set(PARAM.max, String(f.budgetMax));
  if (f.currency && f.currency !== DEFAULT_CURRENCY) p.set(PARAM.currency, f.currency);
  if (f.sort && f.sort !== DEFAULT_SORT) p.set(PARAM.sort, f.sort);
  if (f.page && f.page > 1) p.set(PARAM.page, String(f.page));
  for (const [k, v] of Object.entries(extra)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : '';
}

export function activeFilterCount(f: CallFilters): number {
  return [
    f.q, f.programme?.length, f.regime?.length, f.country?.length,
    f.status !== DEFAULT_STATUS ? f.status : undefined,
    f.deadlineFrom, f.deadlineTo, f.budgetMin, f.budgetMax,
  ].filter((v) => v !== undefined && v !== 0 && v !== '').length;
}

/* ---- Tenders (/tenders) and buyers (/buyers). Same keys and caps as the funding filters. ---- */

export const TENDER_PAGE_SIZE = 10;
export const BUYER_PAGE_SIZE = 20;
export const DEFAULT_TENDER_STATUS: TenderStatusFilter = 'open';
export const DEFAULT_TENDER_SCOPE: TenderScopeFilter = 'core';
export const DEFAULT_TENDER_SORT: TenderSort = 'deadline-asc';
/** Soonest deadline first, except on a closed list: its soonest is years old, so the newest deadline leads. */
export function defaultTenderSort(status: TenderStatusFilter | undefined): TenderSort {
  return status === 'closed' ? 'deadline-desc' : DEFAULT_TENDER_SORT;
}
export const DEFAULT_BUYER_SORT: BuyerSort = 'tenders';

const TENDER_STATUSES: TenderStatusFilter[] = ['open', 'closed', 'all'];
const TENDER_SCOPES: TenderScopeFilter[] = ['core', 'supply', 'all'];
const TENDER_SORTS: TenderSort[] = ['deadline-asc', 'deadline-desc', 'published-desc'];
const BUYER_SORTS: BuyerSort[] = ['tenders', 'name'];
const COUNTRY_CODES: string[] = BUYER_COUNTRY_CODES;

/** CPV prefixes: digits only, 2 to 8 long (a trailing check digit, as in 35120000-1, is dropped), at most 20. */
function cpvList(v: string | string[] | undefined): string[] | undefined {
  if (!v) return undefined;
  const raw = (Array.isArray(v) ? v : [v]).flatMap((s) => s.split(/[,\s]+/));
  const out = raw.map((s) => /^(\d{8})-\d$/.exec(s)?.[1] ?? s).filter((s) => /^\d{2,8}$/.test(s));
  const unique = [...new Set(out)].slice(0, 20);
  return unique.length ? unique : undefined;
}

function pageOf(v: string | undefined): number {
  const n = num(v);
  return n && n >= 1 ? Math.min(Math.floor(n), MAX_PAGE) : 1;
}

/** `buyer` is never read from the URL: the buyer page sets it from the API's own id. */
export function parseTenderFilters(sp: SearchParams): TenderFilters {
  const from = first(sp[PARAM.from]);
  const to = first(sp[PARAM.to]);
  const currency = first(sp[PARAM.currency]);
  const status = oneOf(first(sp[PARAM.status]), TENDER_STATUSES) ?? DEFAULT_TENDER_STATUS;
  return {
    q: searchText(first(sp[PARAM.q])),
    country: list<string>(sp[PARAM.country], COUNTRY_CODES),
    status,
    scope: oneOf(first(sp[PARAM.scope]), TENDER_SCOPES) ?? DEFAULT_TENDER_SCOPE,
    cpv: cpvList(sp[PARAM.cpv]),
    deadlineFrom: from && isDay(from) ? from : undefined,
    deadlineTo: to && isDay(to) ? to : undefined,
    valueMin: num(first(sp[PARAM.min])),
    valueMax: num(first(sp[PARAM.max])),
    currency: currency && CURRENCY_RE.test(currency) ? currency.toUpperCase() : DEFAULT_CURRENCY,
    sort: oneOf(first(sp[PARAM.sort]), TENDER_SORTS) ?? defaultTenderSort(status),
    page: pageOf(first(sp[PARAM.page])),
    pageSize: TENDER_PAGE_SIZE,
  };
}

/** URL / API query for tenders, defaults omitted. Empty string = the unfiltered default list (cacheable). */
export function toTenderQuery(f: TenderFilters): string {
  const p = new URLSearchParams();
  if (f.q) p.set(PARAM.q, f.q);
  if (f.country?.length) p.set(PARAM.country, f.country.join(','));
  if (f.status && f.status !== DEFAULT_TENDER_STATUS) p.set(PARAM.status, f.status);
  if (f.scope && f.scope !== DEFAULT_TENDER_SCOPE) p.set(PARAM.scope, f.scope);
  if (f.cpv?.length) p.set(PARAM.cpv, f.cpv.join(','));
  if (f.buyer) p.set('buyer', f.buyer);
  if (f.deadlineFrom) p.set(PARAM.from, f.deadlineFrom);
  if (f.deadlineTo) p.set(PARAM.to, f.deadlineTo);
  if (f.valueMin !== undefined) p.set(PARAM.min, String(f.valueMin));
  if (f.valueMax !== undefined) p.set(PARAM.max, String(f.valueMax));
  if (f.currency && f.currency !== DEFAULT_CURRENCY) p.set(PARAM.currency, f.currency);
  if (f.sort && f.sort !== defaultTenderSort(f.status)) p.set(PARAM.sort, f.sort);
  if (f.page && f.page > 1) p.set(PARAM.page, String(f.page));
  const s = p.toString();
  return s ? `?${s}` : '';
}

export function activeTenderFilterCount(f: TenderFilters): number {
  return [
    f.q, f.country?.length, f.cpv?.length,
    f.status !== DEFAULT_TENDER_STATUS ? f.status : undefined,
    f.scope !== DEFAULT_TENDER_SCOPE ? f.scope : undefined,
    f.deadlineFrom, f.deadlineTo, f.valueMin, f.valueMax,
  ].filter((v) => v !== undefined && v !== 0 && v !== '').length;
}

export function parseBuyerFilters(sp: SearchParams): BuyerFilters {
  return {
    q: searchText(first(sp[PARAM.q])),
    country: list<string>(sp[PARAM.country], COUNTRY_CODES),
    hasOpen: first(sp[PARAM.hasOpen]) === 'true' ? true : undefined,
    sort: oneOf(first(sp[PARAM.sort]), BUYER_SORTS) ?? DEFAULT_BUYER_SORT,
    page: pageOf(first(sp[PARAM.page])),
    pageSize: BUYER_PAGE_SIZE,
  };
}

export function toBuyerQuery(f: BuyerFilters): string {
  const p = new URLSearchParams();
  if (f.q) p.set(PARAM.q, f.q);
  if (f.country?.length) p.set(PARAM.country, f.country.join(','));
  if (f.hasOpen) p.set(PARAM.hasOpen, 'true');
  if (f.sort && f.sort !== DEFAULT_BUYER_SORT) p.set(PARAM.sort, f.sort);
  if (f.page && f.page > 1) p.set(PARAM.page, String(f.page));
  const s = p.toString();
  return s ? `?${s}` : '';
}

export function activeBuyerFilterCount(f: BuyerFilters): number {
  return [f.q, f.country?.length, f.hasOpen ? 1 : undefined].filter((v) => v !== undefined && v !== 0 && v !== '').length;
}

/* ---- What a list page was asked for and did not use ---- */

export type ListKind = 'tenders' | 'funding' | 'buyers';

/**
 * Notices for the parameters of a list URL that are present but not usable, and for ranges that cannot match.
 * The parsers above drop such a value silently; the page shows these above the results so a mistyped link does
 * not read as "there are no results". Empty values (a form submitted with a blank field) are not mentioned.
 */
export function ignoredFilters(sp: SearchParams, kind: ListKind): string[] {
  const out: string[] = [];
  const bad = (key: string, value: string, why: string) => out.push(`Ignored filter: ${key}=${value.slice(0, 40)} (${why})`);
  const one = (key: string) => (first(sp[key]) ?? '').trim();
  const many = (key: string) => (Array.isArray(sp[key]) ? (sp[key] as string[]) : [sp[key] ?? '']).flatMap((v) => v.split(/[,\s]+/)).map((v) => v.trim()).filter(Boolean);
  const choice = (key: string, allowed: readonly string[]) => {
    const v = one(key);
    if (v && !allowed.includes(v)) bad(key, v, `use ${allowed.join(', ')}`);
  };
  const codes = (key: string, allowed: readonly string[], what: string) => {
    for (const v of many(key)) if (!allowed.includes(v.toUpperCase()) && !allowed.includes(v)) bad(key, v, `not a known ${what}`);
  };
  const day = (key: string) => {
    const v = one(key);
    if (v && !isDay(v)) bad(key, v, 'not a date; use YYYY-MM-DD');
    return v && isDay(v) ? v : null;
  };
  const amount = (key: string) => {
    const v = one(key);
    if (v && num(v) === undefined) bad(key, v, 'not an amount; use digits only');
    return v ? num(v) : undefined;
  };

  if (kind === 'buyers') {
    choice(PARAM.sort, BUYER_SORTS);
    const open = one(PARAM.hasOpen);
    if (open && open !== 'true') bad(PARAM.hasOpen, open, 'use true');
    codes(PARAM.country, COUNTRY_CODES, 'country code');
  } else {
    choice(PARAM.status, kind === 'tenders' ? TENDER_STATUSES : STATUSES);
    choice(PARAM.sort, kind === 'tenders' ? TENDER_SORTS : SORTS);
    if (kind === 'tenders') {
      choice(PARAM.scope, TENDER_SCOPES);
      for (const v of many(PARAM.cpv)) {
        if (!/^(\d{8}-\d|\d{2,8})$/.test(v)) bad(PARAM.cpv, v, 'CPV codes are 2 to 8 digits');
      }
      codes(PARAM.country, COUNTRY_CODES, 'country code');
    } else {
      codes(PARAM.country, Object.keys(COUNTRIES), 'funder country');
      codes(PARAM.programme, PROGRAMME_CODES, 'programme');
      codes(PARAM.regime, REGIME_CODES, 'regime');
    }
    const from = day(PARAM.from);
    const to = day(PARAM.to);
    const min = amount(PARAM.min);
    const max = amount(PARAM.max);
    const cur = one(PARAM.currency);
    if (cur && !CURRENCY_RE.test(cur)) bad(PARAM.currency, cur, 'use a three-letter code such as EUR');
    if (from && to && from > to) out.push(`The date range is inverted: ${from} is after ${to}, so nothing can match. Swap the two dates.`);
    if (min !== undefined && max !== undefined && min > max) out.push(`The ${kind === 'tenders' ? 'value' : 'budget'} range is inverted: the minimum is above the maximum, so nothing can match.`);
  }
  const page = one(PARAM.page);
  if (page && num(page) === undefined) bad(PARAM.page, page, 'not a page number');
  return out;
}

/** The last page that has results (1 when there are none). A page past it is redirected here. */
export function lastPage(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
}
