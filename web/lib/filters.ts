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
  scope: 'scope', hasOpen: 'hasOpen',
} as const;

const STATUSES: CallStatusFilter[] = ['open', 'forthcoming', 'closing-soon', 'closed', 'all'];
const SORTS: CallSort[] = ['deadline-asc', 'deadline-desc', 'budget-desc'];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const CURRENCY_RE = /^[A-Za-z]{3}$/;

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
    deadlineFrom: from && DATE_RE.test(from) ? from : undefined,
    deadlineTo: to && DATE_RE.test(to) ? to : undefined,
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
export const DEFAULT_BUYER_SORT: BuyerSort = 'tenders';

const TENDER_STATUSES: TenderStatusFilter[] = ['open', 'closed', 'all'];
const TENDER_SCOPES: TenderScopeFilter[] = ['core', 'supply', 'all'];
const TENDER_SORTS: TenderSort[] = ['deadline-asc', 'published-desc'];
const BUYER_SORTS: BuyerSort[] = ['tenders', 'name'];
const COUNTRY_CODES: string[] = BUYER_COUNTRY_CODES;

function pageOf(v: string | undefined): number {
  const n = num(v);
  return n && n >= 1 ? Math.min(Math.floor(n), MAX_PAGE) : 1;
}

/** `buyer` is never read from the URL: the buyer page sets it from the API's own id. */
export function parseTenderFilters(sp: SearchParams): TenderFilters {
  const from = first(sp[PARAM.from]);
  const to = first(sp[PARAM.to]);
  const currency = first(sp[PARAM.currency]);
  return {
    q: searchText(first(sp[PARAM.q])),
    country: list<string>(sp[PARAM.country], COUNTRY_CODES),
    status: oneOf(first(sp[PARAM.status]), TENDER_STATUSES) ?? DEFAULT_TENDER_STATUS,
    scope: oneOf(first(sp[PARAM.scope]), TENDER_SCOPES) ?? DEFAULT_TENDER_SCOPE,
    deadlineFrom: from && DATE_RE.test(from) ? from : undefined,
    deadlineTo: to && DATE_RE.test(to) ? to : undefined,
    valueMin: num(first(sp[PARAM.min])),
    valueMax: num(first(sp[PARAM.max])),
    currency: currency && CURRENCY_RE.test(currency) ? currency.toUpperCase() : DEFAULT_CURRENCY,
    sort: oneOf(first(sp[PARAM.sort]), TENDER_SORTS) ?? DEFAULT_TENDER_SORT,
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
  if (f.buyer) p.set('buyer', f.buyer);
  if (f.deadlineFrom) p.set(PARAM.from, f.deadlineFrom);
  if (f.deadlineTo) p.set(PARAM.to, f.deadlineTo);
  if (f.valueMin !== undefined) p.set(PARAM.min, String(f.valueMin));
  if (f.valueMax !== undefined) p.set(PARAM.max, String(f.valueMax));
  if (f.currency && f.currency !== DEFAULT_CURRENCY) p.set(PARAM.currency, f.currency);
  if (f.sort && f.sort !== DEFAULT_TENDER_SORT) p.set(PARAM.sort, f.sort);
  if (f.page && f.page > 1) p.set(PARAM.page, String(f.page));
  const s = p.toString();
  return s ? `?${s}` : '';
}

export function activeTenderFilterCount(f: TenderFilters): number {
  return [
    f.q, f.country?.length,
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
