/**
 * The only data-access module. Pages and components never import lib/mock directly.
 * Set DG_API_URL to talk to the real API. Unset, the site serves mock data in development; a production
 * build or server without it refuses to start (DG_USE_MOCK=1 allows a demo build on purpose).
 * Endpoints and shapes (funding, tenders, buyers): docs/design/API_CONTRACT.md.
 */
import { headers } from 'next/headers';
import type { Buyer, BuyerFilters, BuyerProfile, Call, CallFilters, ChangeFilters, ChangePage, Digest, DigestWeek, Health, MarketFilters, MarketStats, Paginated, ScopeCounts, SiteStats, Supplier, SupplierFilters, SupplierItem, SupplierSummary, Tender, TenderFilters, TenderVersion } from './types';
import { BUYER_PAGE_SIZE, CHANGE_PAGE_SIZE, DEFAULT_PAGE_SIZE, PARAM, TENDER_PAGE_SIZE, toBuyerQuery, toChangeQuery, toQuery, toTenderQuery } from './filters';
import { PLACEHOLDER_AMOUNT_MAX } from './format';
import { now } from './deadline';
import { clientIp } from './hits';
import { recall, remember } from './last-good';
import * as callsMock from './mock/calls';
import * as sourcesMock from './mock/sources';
import * as statsMock from './mock/stats';
import * as supplierMock from './mock/suppliers';
import * as tenderMock from './mock/tenders';

const API_BASE = process.env.DG_API_URL;
const INTERNAL_SECRET = process.env.DG_INTERNAL_SECRET;
// Fail loudly: without the API a production site would serve invented "Demo" tenders and calls, cache them for an
// hour and list their slugs in the sitemap, with no error anywhere (internal audit M4, 14 October 2026).
if (!API_BASE && process.env.NODE_ENV === 'production' && process.env.DG_USE_MOCK !== '1') {
  throw new Error(
    'DG_API_URL is not set. A production build or server needs the API address (http://api:8000 on the compose ' +
      'network); set DG_USE_MOCK=1 only to build a demo with invented data.',
  );
}
/** Detail pages, slugs and statistics: data is collected daily; an hour of ISR is plenty. */
export const REVALIDATE_SECONDS = 3600;
/**
 * The default lists, the home counters and the source status. They carry counts and "closing soon" cards that
 * move when a deadline passes (336 shown against 313 live, cards closed at 12:00 still "Closing soon" at 12:15:
 * site-qa2:N1), so they are as fresh as the API's own list cache (60 s, DGATE_LIST_CACHE_SECONDS) and the pages
 * that read them revalidate at the same rate (`export const revalidate = 60`). Statuses and countdowns are
 * computed at render time from the deadline (lib/deadline.ts), never kept in the payload.
 */
export const LIST_REVALIDATE_SECONDS = 60;
/** One call, notice or buyer: its pages revalidate at this rate too. */
export const DETAIL_REVALIDATE_SECONDS = 300;
const RELATED_LIMIT = 3;
/** A call, tender or buyer slug is "<id>-<words>"; anything else cannot be one and never reaches the API. */
const CALL_SLUG_RE = /^[0-9]{1,9}(-[a-z0-9-]{0,80})?$/;
export function isCallSlug(slug: string): boolean {
  return CALL_SLUG_RE.test(slug);
}
export const isTenderSlug = isCallSlug;
export const isBuyerSlug = isCallSlug;
export const isSupplierSlug = isCallSlug;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/**
 * `revalidate`: shared fetch cache (ISR). `no-store`: used for list requests shaped by visitor input,
 * so arbitrary query strings cannot fill the cache.
 */
export type CacheMode = 'revalidate' | 'no-store';

/**
 * What the API needs to charge a request to the visitor and not to the site's one shared bucket (external audit
 * X-2): the visitor's address as Caddy set it, with the shared secret when there is one. Only for requests that
 * are shaped by the visitor (`no-store`), which are dynamic anyway: reading the request headers in a cached (ISR)
 * fetch would make the page dynamic. Outside a request (build, revalidation) there is no visitor and nothing is sent.
 */
async function visitorHeaders(): Promise<Record<string, string>> {
  try {
    const ip = clientIp((await headers()).get('x-forwarded-for'));
    if (ip === 'unknown') return {};
    return INTERNAL_SECRET ? { 'x-dg-client-ip': ip, 'x-dg-internal': INTERNAL_SECRET } : { 'x-dg-client-ip': ip };
  } catch {
    return {};
  }
}

/** A request the data service has not answered by now is given up: the page then shows its last good answer, or says so. */
const HTTP_TIMEOUT_MS = 20_000;

export async function http<T>(path: string, mode: CacheMode = 'revalidate', seconds: number = REVALIDATE_SECONDS): Promise<T | null> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { accept: 'application/json', ...(mode === 'no-store' ? await visitorHeaders() : {}) },
    signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
    ...(mode === 'no-store' ? { cache: 'no-store' as const } : { next: { revalidate: seconds } }),
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, `GET ${path} failed`);
  return (await res.json()) as T;
}

/** What a detail page gets for something the API answers 410 for: removed on request (see `whenRemoved`). */
export const REMOVED = 'removed' as const;
/** `.catch(whenRemoved)` on a detail fetch: a 410 becomes `REMOVED`, every other failure still throws. */
export function whenRemoved(e: unknown): typeof REMOVED {
  if (e instanceof ApiError && e.status === 410) return REMOVED;
  throw e;
}
export async function httpOrThrow<T>(path: string, mode: CacheMode = 'revalidate', seconds: number = REVALIDATE_SECONDS): Promise<T> {
  const r = await http<T>(path, mode, seconds);
  if (r === null) throw new ApiError(404, `GET ${path} returned 404`);
  return r;
}

/**
 * Run a read; remember a good answer; when the data service does not answer (a timeout, a 5xx), give the last good
 * answer for the same request marked `staleAsOf`, so the page can say "as of" instead of showing dashes or an empty
 * list. A refusal (4xx) and a read that must be live (`allowStale: false`, the CSV export) are never softened.
 * `persist`: also kept on disk, for the answers every visitor shares (default lists, counters, source status).
 */
async function withLastGood<T extends object>(
  key: string, fetcher: () => Promise<T>, opts: { persist?: boolean; allowStale?: boolean } = {},
): Promise<T & { staleAsOf?: string }> {
  try {
    const value = await fetcher();
    await remember(key, value, { persist: opts.persist });
    return value;
  } catch (e) {
    if (opts.allowStale === false || (e instanceof ApiError && e.status >= 400 && e.status < 500)) throw e;
    const kept = await recall<T>(key);
    if (!kept) throw e;
    return { ...kept.value, staleAsOf: kept.at };
  }
}

/** Query for /v1/funding: the site's URL keys (defaults omitted) plus pageSize. */
function fundingQuery(f: CallFilters): string {
  const p = new URLSearchParams(toQuery(f));
  p.set('pageSize', String(f.pageSize ?? DEFAULT_PAGE_SIZE));
  return `?${p.toString()}`;
}

/**
 * Only the unfiltered list (default filters, page 1) is cached. Any q or other filter goes to the API uncached.
 * `cacheable` is for fixed queries written in our own code (e.g. the landing page's closing-soon sample),
 * never for ones built from the URL.
 */
export async function getCalls(filters: CallFilters = {}, opts: { cacheable?: boolean; fresh?: boolean } = {}): Promise<Paginated<Call>> {
  if (API_BASE) {
    // `fresh`: a CSV export reads every page live, so page 1 is not an hour older than page 2.
    const shared = opts.fresh !== true && (opts.cacheable === true || toQuery(filters) === '');
    const path = `/v1/funding${fundingQuery(filters)}`;
    return withLastGood(`funding:${path}`, () => httpOrThrow<Paginated<Call>>(path, shared ? 'revalidate' : 'no-store', LIST_REVALIDATE_SECONDS),
      { persist: shared, allowStale: opts.fresh !== true });
  }
  return callsMock.queryCalls(filters);
}

/** `slug` is "<id>-<words>"; the API looks up the leading id only. Callers redirect when the returned slug differs. */
export async function getCall(slug: string): Promise<Call | null> {
  if (!isCallSlug(slug)) return null;
  if (API_BASE) return http<Call>(`/v1/funding/${encodeURIComponent(slug)}`, 'revalidate', DETAIL_REVALIDATE_SECONDS);
  return callsMock.findCall(slug);
}

/** The open calls a call page picks its related ones from. Start it before the call itself is read: it does not depend on it. */
export const getOpenCallsForRelated = () => getCalls({ status: 'open', pageSize: 50 });

/** The related calls of a call, from the open calls: same programme first, then same funder country. */
export function relatedCallsFrom(call: Call, open: Call[]): Call[] {
  const others = open.filter((c) => c.id !== call.id);
  const score = (c: Call) => (c.programme === call.programme ? 2 : 0) + (c.funderCountry === call.funderCountry ? 1 : 0);
  // A call that shares neither the programme nor the funder country is not related (site-qa2:N15: a Polish, a
  // Swedish and an EU call under a French one): fewer than three, or none, is the honest answer.
  return others.filter((c) => score(c) > 0).sort((a, b) => score(b) - score(a)).slice(0, RELATED_LIMIT);
}

/** Slugs for the sitemap. */
export async function getAllCallSlugs(): Promise<{ slug: string; updatedAt: string }[]> {
  if (API_BASE) return httpOrThrow<{ slug: string; updatedAt: string }[]>('/v1/funding/slugs');
  return callsMock.allCalls().map((c) => ({ slug: c.slug, updatedAt: c.lastSeenAt }));
}

/** Query for /v1/tenders: the site's URL keys (defaults omitted) plus pageSize. */
function tendersQuery(f: TenderFilters): string {
  const p = new URLSearchParams(toTenderQuery(f));
  // A value filter never matches a placeholder amount (0, 0.01, 1): the pages show those as not stated.
  if (f.valueMin !== undefined || f.valueMax !== undefined) {
    p.set(PARAM.min, String(Math.max(f.valueMin ?? 0, PLACEHOLDER_AMOUNT_MAX + 0.01)));
  }
  p.set('pageSize', String(f.pageSize ?? TENDER_PAGE_SIZE));
  return `?${p.toString()}`;
}

/**
 * Same rule as getCalls: only the unfiltered list (default filters, page 1) is cached. Anything built from
 * visitor input goes to the API uncached. `cacheable` is for queries fixed in our own code (a buyer's id comes
 * from the API, not from the URL).
 */
export async function getTenders(filters: TenderFilters = {}, opts: { cacheable?: boolean; fresh?: boolean } = {}): Promise<Paginated<Tender>> {
  if (API_BASE) {
    // `fresh`: a CSV export reads every page live, so page 1 is not an hour older than page 2.
    const shared = opts.fresh !== true && (opts.cacheable === true || toTenderQuery(filters) === '');
    const path = `/v1/tenders${tendersQuery(filters)}`;
    return withLastGood(`tenders:${path}`, () => httpOrThrow<Paginated<Tender>>(path, shared ? 'revalidate' : 'no-store', LIST_REVALIDATE_SECONDS),
      { persist: shared, allowStale: opts.fresh !== true });
  }
  return tenderMock.queryTenders(filters);
}

/**
 * What each scope choice of the tender filter leads to, for the other filters as given (GET /v1/tenders/scope-counts).
 * null when the API cannot say (an older build, or no answer in time): the filter then shows its choices without counts.
 */
export async function getTenderScopeCounts(filters: TenderFilters = {}): Promise<ScopeCounts | null> {
  try {
    if (API_BASE) {
      const p = new URLSearchParams(toTenderQuery({ ...filters, scope: undefined, sort: undefined, page: 1 }));
      for (const k of ['scope', 'sort', 'page']) p.delete(k);
      if (filters.valueMin !== undefined || filters.valueMax !== undefined) p.set(PARAM.min, String(Math.max(filters.valueMin ?? 0, PLACEHOLDER_AMOUNT_MAX + 0.01)));
      const q = p.toString();
      return await http<ScopeCounts>(`/v1/tenders/scope-counts${q ? `?${q}` : ''}`, q === '' ? 'revalidate' : 'no-store', LIST_REVALIDATE_SECONDS);
    }
    const all = tenderMock.queryTenders({ ...filters, scope: 'all', page: 1, pageSize: 100000 }).items;
    const core = all.filter((t) => t.scope === 'core').length;
    const supply = all.filter((t) => t.scope === 'supply').length;
    return { relevant: core + supply, core, supply };
  } catch {
    return null;
  }
}

/**
 * One page of a tenders CSV export: the notices of the same filters, newest first, `limit` at a time (the API
 * allows 2,000), with no total. `nextCursor` goes back as `cursor` until it is null. Always read live.
 */
export async function getTenderExportPage(
  filters: TenderFilters, cursor: string | null, limit: number,
): Promise<{ items: Tender[]; nextCursor: string | null }> {
  if (API_BASE) {
    const p = new URLSearchParams(tendersQuery(filters));
    for (const k of ['page', 'pageSize', 'sort']) p.delete(k);
    p.set('limit', String(limit));
    if (cursor) p.set('cursor', cursor);
    return httpOrThrow<{ items: Tender[]; nextCursor: string | null }>(`/v1/tenders/export?${p.toString()}`, 'no-store');
  }
  const page = cursor ? Number(cursor) : 1;
  const r = tenderMock.queryTenders({ ...filters, page, pageSize: limit });
  return { items: r.items, nextCursor: page * limit < r.total ? String(page + 1) : null };
}

/** `slug` is "<id>-<words>"; the API looks up the leading id only. Callers redirect when the returned slug differs. */
export async function getTender(slug: string): Promise<Tender | null> {
  if (!isTenderSlug(slug)) return null;
  if (API_BASE) return http<Tender>(`/v1/tenders/${encodeURIComponent(slug)}`, 'revalidate', DETAIL_REVALIDATE_SECONDS);
  return tenderMock.findTender(slug);
}

/** The archive of one notice, newest first. */
export async function getTenderVersions(slug: string): Promise<TenderVersion[]> {
  if (!isTenderSlug(slug)) return [];
  if (API_BASE) return (await http<TenderVersion[]>(`/v1/tenders/${encodeURIComponent(slug)}/versions`, 'revalidate', DETAIL_REVALIDATE_SECONDS)) ?? [];
  return tenderMock.tenderVersions(slug) ?? [];
}

/** Slugs for the sitemap (open and last 12 months, core scope, at most 5,000). */
export async function getAllTenderSlugs(): Promise<{ slug: string; updatedAt: string }[]> {
  if (API_BASE) return httpOrThrow<{ slug: string; updatedAt: string }[]>('/v1/tenders/slugs');
  return tenderMock.allTenders().filter((t) => t.scope === 'core').map((t) => ({ slug: t.slug, updatedAt: t.source.retrievedAt }));
}

/**
 * What changed in the last 14 days (GET /v1/changes, kept five minutes on the API). Only the unfiltered first page is
 * shared in the site's cache; a country, a scope or another page is the visitor's own request. null when the endpoint
 * does not exist yet (a site built before the API was updated): the page then says the feed is not available.
 */
const NO_ENDPOINT = Object.freeze({ none: true });
export async function getChanges(filters: ChangeFilters = {}): Promise<ChangePage | null> {
  if (API_BASE) {
    const p = new URLSearchParams(toChangeQuery(filters));
    p.set('pageSize', String(filters.pageSize ?? CHANGE_PAGE_SIZE));
    const path = `/v1/changes?${p.toString()}`;
    const shared = toChangeQuery(filters) === '';
    // `null` is "no such endpoint": not remembered, not a failure.
    const got = await withLastGood(`changes:${path}`, async () => {
      const r = await http<ChangePage>(path, shared ? 'revalidate' : 'no-store', LIST_REVALIDATE_SECONDS);
      return r ?? NO_ENDPOINT;
    }, { persist: shared });
    return got === NO_ENDPOINT ? null : (got as ChangePage);
  }
  return tenderMock.queryChanges(filters);
}

/**
 * One issue of the weekly digest (GET /v1/digest): `week` is YYYY-Www, absent for the latest complete week. An issue
 * does not change once its week has ended, so the site shares one cached answer per week and country. null: no such
 * issue (a week outside the archive, or not ended) or an API build that does not have the endpoint.
 */
export async function getDigest(week?: string, country?: string): Promise<Digest | null> {
  if (!API_BASE) return null;
  const p = new URLSearchParams();
  if (week) p.set('week', week);
  if (country) p.set('country', country);
  const path = `/v1/digest${p.size > 0 ? `?${p.toString()}` : ''}`;
  const got = await withLastGood(`digest:${path}`, async () => (await http<Digest>(path, 'revalidate', LIST_REVALIDATE_SECONDS)) ?? NO_ENDPOINT, { persist: !country });
  return got === NO_ENDPOINT ? null : (got as Digest);
}

/** The issues there are, newest first, with the counts of the stored ones (GET /v1/digest/weeks). Empty when unavailable. */
export async function getDigestWeeks(limit = 52): Promise<DigestWeek[]> {
  if (!API_BASE) return [];
  return (await http<DigestWeek[]>(`/v1/digest/weeks?limit=${limit}`, 'revalidate', LIST_REVALIDATE_SECONDS)) ?? [];
}

function buyersQuery(f: BuyerFilters): string {
  const p = new URLSearchParams(toBuyerQuery(f));
  p.set('pageSize', String(f.pageSize ?? BUYER_PAGE_SIZE));
  return `?${p.toString()}`;
}

export async function getBuyers(filters: BuyerFilters = {}): Promise<Paginated<Buyer>> {
  if (API_BASE) {
    return httpOrThrow<Paginated<Buyer>>(`/v1/buyers${buyersQuery(filters)}`, toBuyerQuery(filters) === '' ? 'revalidate' : 'no-store', LIST_REVALIDATE_SECONDS);
  }
  return tenderMock.queryBuyers(filters);
}

const SUPPLIER_PAGE_SIZE = 20;

/** The supplier map's list (GET /v1/suppliers). Without the API (a demo build) it is five invented companies (lib/mock/suppliers.ts). */
export async function getSuppliers(f: SupplierFilters = {}): Promise<Paginated<SupplierItem>> {
  if (!API_BASE) return supplierMock.querySuppliers({ ...f, pageSize: f.pageSize ?? SUPPLIER_PAGE_SIZE });
  const p = new URLSearchParams();
  if (f.q) p.set('q', f.q);
  if (f.country) p.set('country', f.country);
  if (f.cpv) p.set('cpv', f.cpv);
  if (f.sort && f.sort !== 'awards') p.set('sort', f.sort);
  if (f.page && f.page > 1) p.set('page', String(f.page));
  const filtered = p.size > 0;
  p.set('pageSize', String(f.pageSize ?? SUPPLIER_PAGE_SIZE));
  return httpOrThrow<Paginated<SupplierItem>>(`/v1/suppliers?${p.toString()}`, filtered ? 'no-store' : 'revalidate', LIST_REVALIDATE_SECONDS);
}

/** The public aggregate (GET /v1/suppliers/summary). null when the API has no supplier map yet. */
export async function getSupplierSummary(): Promise<SupplierSummary | null> {
  if (!API_BASE) return supplierMock.supplierSummary();
  try {
    return await http<SupplierSummary>('/v1/suppliers/summary', 'revalidate', DETAIL_REVALIDATE_SECONDS);
  } catch {
    return null;
  }
}

export async function getSupplier(slug: string): Promise<Supplier | null> {
  if (!isSupplierSlug(slug)) return null;
  if (!API_BASE) return supplierMock.findSupplier(slug);
  return http<Supplier>(`/v1/suppliers/${encodeURIComponent(slug)}`, 'revalidate', DETAIL_REVALIDATE_SECONDS);
}

export async function getBuyer(slug: string): Promise<Buyer | null> {
  if (!isBuyerSlug(slug)) return null;
  if (API_BASE) return http<Buyer>(`/v1/buyers/${encodeURIComponent(slug)}`, 'revalidate', DETAIL_REVALIDATE_SECONDS);
  return tenderMock.findBuyer(slug);
}

/**
 * The market overview: counts of core-scope notices (GET /v1/stats/market, cached an hour on the API). null only
 * when the endpoint does not exist yet (a site built before the API was updated). Any other failure throws, so a
 * page already built keeps being served and the next visit retries: a page that rendered "not available" would be
 * kept for an hour.
 */
export async function getMarketStats(filters: MarketFilters = {}): Promise<MarketStats | null> {
  if (!API_BASE) return statsMock.marketStats();
  const p = new URLSearchParams();
  if (filters.year) p.set('year', String(filters.year));
  if (filters.country) p.set('country', filters.country);
  const q = p.toString();
  return http<MarketStats>(`/v1/stats/market${q ? `?${q}` : ''}`, q ? 'no-store' : 'revalidate');
}

/** A buyer's own figures (GET /v1/buyers/{slug}/profile). null when there are none or the API cannot answer. */
export async function getBuyerProfile(buyer: Buyer): Promise<BuyerProfile | null> {
  if (!isBuyerSlug(buyer.slug)) return null;
  if (!API_BASE) return statsMock.buyerProfile(buyer);
  try {
    return await http<BuyerProfile>(`/v1/buyers/${encodeURIComponent(buyer.slug)}/profile`);
  } catch {
    return null;
  }
}

/** Slugs for the sitemap (buyers with an open tender, at most 2,000). */
export async function getAllBuyerSlugs(): Promise<{ slug: string; updatedAt: string }[]> {
  if (API_BASE) return httpOrThrow<{ slug: string; updatedAt: string }[]>('/v1/buyers/slugs');
  return tenderMock.allBuyers().filter((b) => b.openCount > 0).map((b) => ({ slug: b.slug, updatedAt: b.lastPublishedAt ?? new Date().toISOString() }));
}

/** Source list with run status: GET /v1/sources (the design's Health). */
export async function getHealth(): Promise<Health> {
  if (API_BASE) return withLastGood('health', () => httpOrThrow<Health>('/v1/sources', 'revalidate', LIST_REVALIDATE_SECONDS), { persist: true });
  return sourcesMock.health();
}

/** Landing counters: open calls from the list total, sources from /v1/sources, last update from generatedAt. */
export async function getSiteStats(): Promise<SiteStats> {
  const [open, health] = await Promise.all([getCalls({ status: 'open', pageSize: 1 }), getHealth()]);
  return { openCalls: open.total, sources: health.sources.length, lastUpdate: lastDataUpdate(health) };
}

/** When data last arrived: the newest source run. `generatedAt` is only when the status was rendered. */
export function lastDataUpdate(health: { generatedAt: string; sources: { lastRunAt: string | null }[] }): string {
  const runs = health.sources.map((s) => s.lastRunAt).filter((t): t is string => Boolean(t)).sort();
  return runs.length > 0 ? runs[runs.length - 1] : health.generatedAt;
}

export { now };
