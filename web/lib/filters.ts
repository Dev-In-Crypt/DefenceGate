import type {
  BuyerFilters, BuyerSort, CallFilters, CallSort, CallStatusFilter, ChangeFilters, CountryCode, ListView, ProgrammeCode, Regime,
  TenderFilters, TenderScopeFilter, TenderSort, TenderStatusFilter,
} from './types';
import { BUYER_COUNTRY_CODES, COUNTRIES, PROGRAMME_CODES, REGIME_CODES, countryName } from './taxonomy';

/** Next.js page searchParams shape. */
export type SearchParams = Record<string, string | string[] | undefined>;

export const DEFAULT_PAGE_SIZE = 10;
export const DEFAULT_SORT: CallSort = 'deadline-asc';
/** Soonest deadline first, except on a closed list: its soonest is the oldest, so the newest deadline leads. */
export function defaultCallSort(status: CallStatusFilter | undefined): CallSort {
  return status === 'closed' ? 'deadline-desc' : DEFAULT_SORT;
}
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
  scope: 'scope', goods: 'goods', hasOpen: 'hasOpen', cpv: 'cpv', year: 'year', cascade: 'cascade', ukraine: 'ukraine',
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

const upper = (s: string) => s.toUpperCase();

function first(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}
/** `fold` normalises each token before it is matched (country codes are upper case: `de` was silently dropped). */
function list<T extends string>(v: string | string[] | undefined, allowed: readonly T[], fold?: (s: string) => string): T[] | undefined {
  if (!v) return undefined;
  const raw = (Array.isArray(v) ? v : [v]).flatMap((s) => s.split(','));
  const out = raw.map((s) => (fold ? fold(s.trim()) : s.trim())).filter((s): s is T => (allowed as readonly string[]).includes(s));
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
  const status = oneOf(first(sp[PARAM.status]), STATUSES) ?? DEFAULT_STATUS;
  return {
    q: searchText(first(sp[PARAM.q])),
    programme: list<ProgrammeCode>(sp[PARAM.programme], PROGRAMME_CODES, upper),
    regime: list<Regime>(sp[PARAM.regime], REGIME_CODES),
    country: list<CountryCode>(sp[PARAM.country], Object.keys(COUNTRIES) as CountryCode[], upper),
    status,
    deadlineFrom: from && isDay(from) ? from : undefined,
    deadlineTo: to && isDay(to) ? to : undefined,
    budgetMin: num(first(sp[PARAM.min])),
    budgetMax: num(first(sp[PARAM.max])),
    // Only a currency the visitor chose: alone it lists the calls that state a budget in it; with a range it is the unit.
    currency: currency && CURRENCY_RE.test(currency) ? currency.toUpperCase() : undefined,
    sort: oneOf(first(sp[PARAM.sort]), SORTS) ?? defaultCallSort(status),
    cascade: first(sp[PARAM.cascade]) === 'true' ? true : undefined,
    ukraine: first(sp[PARAM.ukraine]) === 'true' ? true : undefined,
    page: page && page >= 1 ? Math.min(Math.floor(page), MAX_PAGE) : 1,
    pageSize: DEFAULT_PAGE_SIZE,
  };
}

/**
 * WP-87: where the dual-use calls start on a page of the default order (the API lists the defence calls first, then the dual-use
 * ones): the index of the first dual-use call on the page. -1 when the order was chosen (the regimes are mixed then) or the page
 * has no dual-use call.
 */
export function dualUseStart(items: { regime?: string }[], defaultOrder: boolean): number {
  return defaultOrder ? items.findIndex((c) => c.regime === 'dual-use') : -1;
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
  if (f.currency) p.set(PARAM.currency, f.currency);
  if (f.sort && f.sort !== defaultCallSort(f.status)) p.set(PARAM.sort, f.sort);
  if (f.cascade) p.set(PARAM.cascade, 'true');
  if (f.ukraine) p.set(PARAM.ukraine, 'true');
  if (f.page && f.page > 1) p.set(PARAM.page, String(f.page));
  for (const [k, v] of Object.entries(extra)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : '';
}

export function activeFilterCount(f: CallFilters): number {
  return [
    f.q, f.programme?.length, f.regime?.length, f.country?.length,
    f.status !== DEFAULT_STATUS ? f.status : undefined,
    f.deadlineFrom, f.deadlineTo, f.budgetMin, f.budgetMax, f.currency, f.cascade ? 'cascade' : undefined, f.ukraine ? 'ukraine' : undefined,
  ].filter((v) => v !== undefined && v !== 0 && v !== '').length;
}

/* ---- An empty funding list: what was asked, and what would find something ---- */

const STATUS_WORDS: Record<CallStatusFilter, string> = {
  open: 'Open', forthcoming: 'Opens soon', 'closing-soon': 'Closing soon', closed: 'Closed', all: 'All',
};

/** The filters in force, in words, for "No calls match ...". The default status is not a choice and is named too. */
export function describeCallFilters(f: CallFilters): string[] {
  const out: string[] = [];
  if (f.q) out.push(`the search “${f.q}”`);
  out.push(`status ${STATUS_WORDS[f.status ?? DEFAULT_STATUS]}`);
  if (f.programme?.length) out.push(`programme ${f.programme.join(', ')}`);
  if (f.regime?.length) out.push(`regime ${f.regime.join(', ')}`);
  if (f.country?.length) out.push(`funder country ${f.country.join(', ')}`);
  if (f.deadlineFrom || f.deadlineTo) out.push(`deadline ${f.deadlineFrom ?? '…'} to ${f.deadlineTo ?? '…'}`);
  if (f.budgetMin !== undefined || f.budgetMax !== undefined) out.push(`budget ${f.budgetMin ?? 0} to ${f.budgetMax ?? '∞'} ${f.currency ?? DEFAULT_CURRENCY}`);
  else if (f.currency) out.push(`a budget stated in ${f.currency}`);
  if (f.cascade) out.push('financial support to third parties');
  if (f.ukraine) out.push('open to Ukrainian participants');
  return out;
}

export interface Broadening {
  /** Completes "N calls match ...": "in all statuses", "without the search “x”". */
  label: string;
  filters: CallFilters;
}

/** Each way of loosening one filter of an empty list, the likeliest culprit first: the search, then the status. */
export function broadenings(f: CallFilters): Broadening[] {
  const base = { ...f, page: 1 };
  const out: Broadening[] = [];
  if (f.q) out.push({ label: `without the search “${f.q}”`, filters: { ...base, q: undefined } });
  if ((f.status ?? DEFAULT_STATUS) !== 'all') out.push({ label: 'in all statuses, closed ones too', filters: { ...base, status: 'all', sort: undefined } });
  if (f.programme?.length) out.push({ label: 'in every programme', filters: { ...base, programme: undefined } });
  if (f.regime?.length) out.push({ label: 'with either regime', filters: { ...base, regime: undefined } });
  if (f.country?.length) out.push({ label: 'from any funder country', filters: { ...base, country: undefined } });
  if (f.deadlineFrom || f.deadlineTo) out.push({ label: 'with any deadline', filters: { ...base, deadlineFrom: undefined, deadlineTo: undefined } });
  if (f.budgetMin !== undefined || f.budgetMax !== undefined) out.push({ label: 'with any budget', filters: { ...base, budgetMin: undefined, budgetMax: undefined } });
  if (f.cascade) out.push({ label: 'without the financial-support filter', filters: { ...base, cascade: undefined } });
  if (f.ukraine) out.push({ label: 'without the Ukraine filter', filters: { ...base, ukraine: undefined } });
  return out;
}

/* ---- Tenders (/tenders) and buyers (/buyers). Same keys and caps as the funding filters. ---- */

export const TENDER_PAGE_SIZE = 10;
export const BUYER_PAGE_SIZE = 20;
export const DEFAULT_TENDER_STATUS: TenderStatusFilter = 'open';
export const DEFAULT_TENDER_SCOPE: TenderScopeFilter = 'relevant';
export const DEFAULT_TENDER_SORT: TenderSort = 'deadline-asc';
/**
 * Soonest deadline first, except on a closed or planned list (the API's own default): the newest deadline leads. WP-87: the
 * open list leads with the military goods and works (`core-first`, the API's default for it), each part soonest first.
 */
export function defaultTenderSort(status: TenderStatusFilter | undefined): TenderSort {
  if (status === undefined || status === 'open') return 'core-first';
  return status === 'closed' || status === 'planned' ? 'deadline-desc' : DEFAULT_TENDER_SORT;
}
export const DEFAULT_BUYER_SORT: BuyerSort = 'tenders';

const TENDER_STATUSES: TenderStatusFilter[] = ['open', 'closed', 'planned', 'all'];
const TENDER_SCOPES: TenderScopeFilter[] = ['relevant', 'core', 'supply', 'all'];
const GOODS = ['defence'] as const;
const TENDER_SORTS: TenderSort[] = ['core-first', 'deadline-asc', 'deadline-desc', 'published-desc'];
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
    country: list<string>(sp[PARAM.country], COUNTRY_CODES, upper),
    status,
    scope: oneOf(first(sp[PARAM.scope]), TENDER_SCOPES) ?? DEFAULT_TENDER_SCOPE,
    goods: oneOf(first(sp[PARAM.goods]), GOODS),
    cpv: cpvList(sp[PARAM.cpv]),
    deadlineFrom: from && isDay(from) ? from : undefined,
    deadlineTo: to && isDay(to) ? to : undefined,
    valueMin: num(first(sp[PARAM.min])),
    valueMax: num(first(sp[PARAM.max])),
    // Only a currency the visitor chose: alone it lists the notices that state a value in it; with a range it is the unit.
    currency: currency && CURRENCY_RE.test(currency) ? currency.toUpperCase() : undefined,
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
  if (f.goods) p.set(PARAM.goods, f.goods);
  if (f.cpv?.length) p.set(PARAM.cpv, f.cpv.join(','));
  if (f.buyer) p.set('buyer', f.buyer);
  if (f.deadlineFrom) p.set(PARAM.from, f.deadlineFrom);
  if (f.deadlineTo) p.set(PARAM.to, f.deadlineTo);
  if (f.valueMin !== undefined) p.set(PARAM.min, String(f.valueMin));
  if (f.valueMax !== undefined) p.set(PARAM.max, String(f.valueMax));
  if (f.currency) p.set(PARAM.currency, f.currency);
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
    f.goods,
    f.deadlineFrom, f.deadlineTo, f.valueMin, f.valueMax, f.currency,
  ].filter((v) => v !== undefined && v !== 0 && v !== '').length;
}

export function parseBuyerFilters(sp: SearchParams): BuyerFilters {
  return {
    q: searchText(first(sp[PARAM.q])),
    country: list<string>(sp[PARAM.country], COUNTRY_CODES, upper),
    cpv: cpvList(sp[PARAM.cpv]),
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
  if (f.cpv?.length) p.set(PARAM.cpv, f.cpv.join(','));
  if (f.hasOpen) p.set(PARAM.hasOpen, 'true');
  if (f.sort && f.sort !== DEFAULT_BUYER_SORT) p.set(PARAM.sort, f.sort);
  if (f.page && f.page > 1) p.set(PARAM.page, String(f.page));
  const s = p.toString();
  return s ? `?${s}` : '';
}

export function activeBuyerFilterCount(f: BuyerFilters): number {
  return [f.q, f.country?.length, f.cpv?.length, f.hasOpen ? 1 : undefined].filter((v) => v !== undefined && v !== 0 && v !== '').length;
}

/* ---- What changed (/changes): country and scope only; 14 days is the API's window ---- */

export const CHANGE_PAGE_SIZE = 25;
/** The API serves the change list up to page 100 (`/v1/changes`, `page <= 100`); a page past it is shown as past the end (QA m-8). */
export const CHANGE_MAX_PAGE = 100;
/** An ISO week as the digest names it. The API settles whether the week exists (404). */
const WEEK_RE = /^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$/;
const CHANGE_KINDS = ['new', 'amended'] as const;

export function parseChangeFilters(sp: SearchParams): ChangeFilters {
  // `relevant` is the API's default for the change list too: left out, like the tender list does.
  const asked = oneOf(first(sp[PARAM.scope]), TENDER_SCOPES);
  const scope = asked === DEFAULT_TENDER_SCOPE ? undefined : asked;
  const goods = oneOf(first(sp[PARAM.goods]), GOODS);
  const week = first(sp.week);
  const kind = oneOf(first(sp.kind), CHANGE_KINDS);
  // WP-87: the tender list's other filters, so a filtered list and its changes (and their Atom feed) hold the same notices
  const t = parseTenderFilters(sp);
  return {
    country: list<string>(sp[PARAM.country], COUNTRY_CODES, upper),
    scope,
    ...(goods ? { goods } : {}),
    ...(t.q ? { q: t.q } : {}),
    ...(t.cpv ? { cpv: t.cpv } : {}),
    ...(t.deadlineFrom ? { deadlineFrom: t.deadlineFrom } : {}),
    ...(t.deadlineTo ? { deadlineTo: t.deadlineTo } : {}),
    ...(t.valueMin !== undefined ? { valueMin: t.valueMin } : {}),
    ...(t.valueMax !== undefined ? { valueMax: t.valueMax } : {}),
    ...(t.currency ? { currency: t.currency } : {}),
    // A week of the digest, and one kind of change in it. `kind` alone is read too: the last 14 days, new or amended only.
    ...(week && WEEK_RE.test(week) ? { week } : {}),
    ...(kind ? { kind } : {}),
    page: pageOf(first(sp[PARAM.page])),
    pageSize: CHANGE_PAGE_SIZE,
  };
}

/** URL / API query for the change list, defaults omitted. Empty: the default list (cacheable). */
export function toChangeQuery(f: ChangeFilters): string {
  const p = new URLSearchParams();
  if (f.country?.length) p.set(PARAM.country, f.country.join(','));
  if (f.scope) p.set(PARAM.scope, f.scope);
  if (f.goods) p.set(PARAM.goods, f.goods);
  if (f.q) p.set(PARAM.q, f.q);
  if (f.cpv?.length) p.set(PARAM.cpv, f.cpv.join(','));
  if (f.deadlineFrom) p.set(PARAM.from, f.deadlineFrom);
  if (f.deadlineTo) p.set(PARAM.to, f.deadlineTo);
  if (f.valueMin !== undefined) p.set(PARAM.min, String(f.valueMin));
  if (f.valueMax !== undefined) p.set(PARAM.max, String(f.valueMax));
  if (f.currency) p.set(PARAM.currency, f.currency);
  if (f.week) p.set('week', f.week);
  if (f.kind) p.set('kind', f.kind);
  if (f.page && f.page > 1) p.set(PARAM.page, String(f.page));
  const s = p.toString();
  return s ? `?${s}` : '';
}

/* ---- Market overview (/market): a calendar year and one buyer country ---- */

/** The first year the market page offers: the archive holds notices back to 2021, and TED history before 2024 is partial. */
export const MARKET_FIRST_YEAR = 2021;

export function parseMarketFilters(sp: SearchParams, thisYear: number = new Date().getUTCFullYear()): { year?: number; country?: string; cpv?: string[] } {
  const y = Number(first(sp[PARAM.year]));
  const year = Number.isInteger(y) && y >= MARKET_FIRST_YEAR && y <= thisYear ? y : undefined;
  const c = (first(sp[PARAM.country]) ?? '').trim().toUpperCase();
  const country = COUNTRY_CODES.includes(c) ? c : undefined;
  const cpv = cpvList(sp[PARAM.cpv]);           // WP-89: as on /tenders
  return { ...(year ? { year } : {}), ...(country ? { country } : {}), ...(cpv ? { cpv } : {}) };
}

/* ---- What a list page was asked for and did not use ---- */

export type ListKind = 'tenders' | 'funding' | 'buyers' | 'changes' | 'organisations' | 'suppliers';

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

  const pageNumber = () => {
    const page = one(PARAM.page);
    if (page && num(page) === undefined) bad(PARAM.page, page, 'not a page number');
    else if (page && (num(page) as number) < 1) bad(PARAM.page, page, 'pages start at 1');
  };
  // WP-73 (QA m-10): the lists that dropped such values silently say so too
  if (kind === 'changes') {
    codes(PARAM.country, COUNTRY_CODES, 'country code');
    choice(PARAM.scope, TENDER_SCOPES);
    choice(PARAM.goods, GOODS);
    choice('kind', CHANGE_KINDS);
    const week = one('week');
    if (week && !WEEK_RE.test(week)) bad('week', week, 'not a week; use YYYY-Www, for example 2026-W42');
    for (const v of many(PARAM.cpv)) if (!/^(\d{8}-\d|\d{2,8})$/.test(v)) bad(PARAM.cpv, v, 'CPV codes are 2 to 8 digits');
    day(PARAM.from);
    day(PARAM.to);
    amount(PARAM.min);
    amount(PARAM.max);
    const cur = one(PARAM.currency);
    if (cur && !CURRENCY_RE.test(cur)) bad(PARAM.currency, cur, 'use a three-letter code such as EUR');
    pageNumber();
    out.push(...unknownParams(sp, CHANGE_PARAMS));
    return out;
  }
  if (kind === 'organisations') {
    for (const v of many(PARAM.country)) if (!/^[A-Za-z]{2}$/.test(v) || countryName(v.toUpperCase()) === v.toUpperCase()) bad(PARAM.country, v, 'not a known country code');
    choice(PARAM.sort, ORG_SORT_VALUES);
    pageNumber();
    return out;
  }
  if (kind === 'suppliers') {
    for (const v of many(PARAM.cpv)) if (!/^\d{2,8}$/.test(v)) bad(PARAM.cpv, v, 'CPV codes are 2 to 8 digits');
    choice(PARAM.sort, ['awards', 'name']);
    pageNumber();
    return out;
  }
  if (kind === 'buyers') {
    choice(PARAM.sort, BUYER_SORTS);
    for (const v of many(PARAM.cpv)) if (!/^(\d{8}-\d|\d{2,8})$/.test(v)) bad(PARAM.cpv, v, 'CPV codes are 2 to 8 digits');
    const open = one(PARAM.hasOpen);
    if (open && open !== 'true') bad(PARAM.hasOpen, open, 'use true');
    codes(PARAM.country, COUNTRY_CODES, 'country code');
  } else {
    choice(PARAM.status, kind === 'tenders' ? TENDER_STATUSES : STATUSES);
    choice(PARAM.sort, kind === 'tenders' ? TENDER_SORTS : SORTS);
    if (kind === 'tenders') {
      choice(PARAM.scope, TENDER_SCOPES);
      choice(PARAM.goods, GOODS);
      for (const v of many(PARAM.cpv)) {
        if (!/^(\d{8}-\d|\d{2,8})$/.test(v)) bad(PARAM.cpv, v, 'CPV codes are 2 to 8 digits');
      }
      codes(PARAM.country, COUNTRY_CODES, 'country code');
    } else {
      codes(PARAM.country, Object.keys(COUNTRIES), 'funder country');
      codes(PARAM.programme, PROGRAMME_CODES, 'programme');
      codes(PARAM.regime, REGIME_CODES, 'regime');
      choice(PARAM.cascade, ['true']);
      choice(PARAM.ukraine, ['true']);
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
  pageNumber();
  return out;
}

/** The parameters /changes and /changes.atom read (WP-87): the tender list's filters, the digest week and the kind of change. */
export const CHANGE_PARAMS = ['country', 'scope', 'goods', 'q', 'cpv', 'from', 'to', 'min', 'max', 'currency', 'week', 'kind', 'page'] as const;
/** The parameters /calendar and /calendar.ics read (WP-87): its own (kind, view, month, page) and the tender list's filters. */
export const CALENDAR_PARAMS = ['kind', 'country', 'view', 'month', 'page', 'q', 'cpv', 'scope', 'goods', 'from', 'to', 'min', 'max', 'currency'] as const;

/**
 * WP-87: a parameter a page does not read is said, never dropped in silence ("/changes?cpv=35" listed every change as if the
 * code had been read). Empty values (a blank form field) are not mentioned; `utm_*` and the like are named like any other.
 */
export function unknownParams(sp: SearchParams, known: readonly string[]): string[] {
  return Object.keys(sp)
    .filter((k) => !known.includes(k) && (Array.isArray(sp[k]) ? (sp[k] as string[]).some((v) => v.trim() !== '') : (sp[k] ?? '').trim() !== ''))
    .sort()
    .map((k) => `Ignored filter: ${k.slice(0, 40)} (not a filter of this page)`);
}

/** The sorts of the organisation list (lib/networks.ts ORG_SORTS), here to keep this file free of the networks module. */
const ORG_SORT_VALUES = ['defence', 'projects', 'name'] as const;

/** The last page that has results (1 when there are none). A page past it is redirected here. */
export function lastPage(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
}
