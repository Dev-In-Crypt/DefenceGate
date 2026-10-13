/**
 * The only data-access module. Pages and components never import lib/mock directly.
 * Set DG_API_URL to talk to the real API; leave it unset to serve mock data.
 * Endpoints and shapes (funding, tenders, buyers): docs/design/API_CONTRACT.md.
 */
import type { Buyer, BuyerFilters, BuyerProfile, Call, CallFilters, Health, MarketStats, Paginated, SiteStats, Tender, TenderFilters, TenderVersion } from './types';
import { BUYER_PAGE_SIZE, DEFAULT_PAGE_SIZE, PARAM, TENDER_PAGE_SIZE, toBuyerQuery, toQuery, toTenderQuery } from './filters';
import { PLACEHOLDER_AMOUNT_MAX } from './format';
import { now } from './deadline';
import * as callsMock from './mock/calls';
import * as sourcesMock from './mock/sources';
import * as statsMock from './mock/stats';
import * as tenderMock from './mock/tenders';

const API_BASE = process.env.DG_API_URL;
/** Data is collected daily; an hour of ISR keeps countdowns fresh. */
export const REVALIDATE_SECONDS = 3600;
const RELATED_LIMIT = 3;
/** A call, tender or buyer slug is "<id>-<words>"; anything else cannot be one and never reaches the API. */
const CALL_SLUG_RE = /^[0-9]{1,9}(-[a-z0-9-]{0,80})?$/;
export function isCallSlug(slug: string): boolean {
  return CALL_SLUG_RE.test(slug);
}
export const isTenderSlug = isCallSlug;
export const isBuyerSlug = isCallSlug;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/**
 * `revalidate`: shared fetch cache (ISR). `no-store`: used for list requests shaped by visitor input,
 * so arbitrary query strings cannot fill the cache.
 */
type CacheMode = 'revalidate' | 'no-store';

async function http<T>(path: string, mode: CacheMode = 'revalidate'): Promise<T | null> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { accept: 'application/json' },
    ...(mode === 'no-store' ? { cache: 'no-store' as const } : { next: { revalidate: REVALIDATE_SECONDS } }),
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, `GET ${path} failed`);
  return (await res.json()) as T;
}
async function httpOrThrow<T>(path: string, mode: CacheMode = 'revalidate'): Promise<T> {
  const r = await http<T>(path, mode);
  if (r === null) throw new ApiError(404, `GET ${path} returned 404`);
  return r;
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
    return httpOrThrow<Paginated<Call>>(`/v1/funding${fundingQuery(filters)}`, shared ? 'revalidate' : 'no-store');
  }
  return callsMock.queryCalls(filters);
}

/** `slug` is "<id>-<words>"; the API looks up the leading id only. Callers redirect when the returned slug differs. */
export async function getCall(slug: string): Promise<Call | null> {
  if (!isCallSlug(slug)) return null;
  if (API_BASE) return http<Call>(`/v1/funding/${encodeURIComponent(slug)}`);
  return callsMock.findCall(slug);
}

/** Same programme first, then same funder country; open calls only. */
export async function getRelatedCalls(call: Call): Promise<Call[]> {
  const { items } = await getCalls({ status: 'open', pageSize: 50 });
  const others = items.filter((c) => c.id !== call.id);
  const score = (c: Call) => (c.programme === call.programme ? 2 : 0) + (c.funderCountry === call.funderCountry ? 1 : 0);
  return others.sort((a, b) => score(b) - score(a)).slice(0, RELATED_LIMIT);
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
    return httpOrThrow<Paginated<Tender>>(`/v1/tenders${tendersQuery(filters)}`, shared ? 'revalidate' : 'no-store');
  }
  return tenderMock.queryTenders(filters);
}

/** `slug` is "<id>-<words>"; the API looks up the leading id only. Callers redirect when the returned slug differs. */
export async function getTender(slug: string): Promise<Tender | null> {
  if (!isTenderSlug(slug)) return null;
  if (API_BASE) return http<Tender>(`/v1/tenders/${encodeURIComponent(slug)}`);
  return tenderMock.findTender(slug);
}

/** The archive of one notice, newest first. */
export async function getTenderVersions(slug: string): Promise<TenderVersion[]> {
  if (!isTenderSlug(slug)) return [];
  if (API_BASE) return (await http<TenderVersion[]>(`/v1/tenders/${encodeURIComponent(slug)}/versions`)) ?? [];
  return tenderMock.tenderVersions(slug) ?? [];
}

/** Slugs for the sitemap (open and last 12 months, core scope, at most 5,000). */
export async function getAllTenderSlugs(): Promise<{ slug: string; updatedAt: string }[]> {
  if (API_BASE) return httpOrThrow<{ slug: string; updatedAt: string }[]>('/v1/tenders/slugs');
  return tenderMock.allTenders().filter((t) => t.scope === 'core').map((t) => ({ slug: t.slug, updatedAt: t.source.retrievedAt }));
}

function buyersQuery(f: BuyerFilters): string {
  const p = new URLSearchParams(toBuyerQuery(f));
  p.set('pageSize', String(f.pageSize ?? BUYER_PAGE_SIZE));
  return `?${p.toString()}`;
}

export async function getBuyers(filters: BuyerFilters = {}): Promise<Paginated<Buyer>> {
  if (API_BASE) {
    return httpOrThrow<Paginated<Buyer>>(`/v1/buyers${buyersQuery(filters)}`, toBuyerQuery(filters) === '' ? 'revalidate' : 'no-store');
  }
  return tenderMock.queryBuyers(filters);
}

export async function getBuyer(slug: string): Promise<Buyer | null> {
  if (!isBuyerSlug(slug)) return null;
  if (API_BASE) return http<Buyer>(`/v1/buyers/${encodeURIComponent(slug)}`);
  return tenderMock.findBuyer(slug);
}

/**
 * The market overview: counts of core-scope notices (GET /v1/stats/market, cached an hour on the API). null only
 * when the endpoint does not exist yet (a site built before the API was updated). Any other failure throws, so a
 * page already built keeps being served and the next visit retries: a page that rendered "not available" would be
 * kept for an hour.
 */
export async function getMarketStats(): Promise<MarketStats | null> {
  if (!API_BASE) return statsMock.marketStats();
  return http<MarketStats>('/v1/stats/market');
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
  if (API_BASE) return httpOrThrow<Health>('/v1/sources');
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
