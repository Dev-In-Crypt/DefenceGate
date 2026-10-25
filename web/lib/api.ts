/**
 * The only data-access module. Pages and components never import lib/mock directly.
 * Set DG_API_URL to talk to the real API. Unset, the site serves mock data in development; a production
 * build or server without it refuses to start (DG_USE_MOCK=1 allows a demo build on purpose).
 * Endpoints and shapes (funding, tenders, buyers): docs/design/API_CONTRACT.md.
 */
import { headers } from 'next/headers';
import { TtlCache } from './export-cache';
import type { ValueSum } from './value-totals';
import type { Buyer, BuyerFilters, BuyerProfile, BuyerSuppliers, CalendarPage, Call, CallFilters, ChangeFilters, ChangePage, Digest, DigestWeek, Health, MarketFilters, MarketStats, Paginated, ScopeCounts, SiteStats, Supplier, SupplierContracts, SupplierFilters, SupplierItem, SupplierSummary, Tender, TenderFilters, TenderVersion } from './types';
import { BUYER_PAGE_SIZE, CHANGE_PAGE_SIZE, DEFAULT_PAGE_SIZE, PARAM, TENDER_PAGE_SIZE, toBuyerQuery, toChangeQuery, toQuery, toTenderQuery } from './filters';
import { PLACEHOLDER_AMOUNT_MAX } from './format';
import { now } from './deadline';
import { FEED_MAX } from './analyst';
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

/**
 * WP-127: how long a request is tried again when the data service cannot be reached at all (its container is being replaced in a
 * deploy: the name does not resolve or the port refuses, a few seconds). Only a failed connection is retried, never an answer.
 */
const UNREACHABLE_RETRY_MS = 15_000;
const UNREACHABLE_PAUSE_MS = 500;

export async function http<T>(path: string, mode: CacheMode = 'revalidate', seconds: number = REVALIDATE_SECONDS): Promise<T | null> {
  const extra = mode === 'no-store' ? await visitorHeaders() : {};
  const until = Date.now() + UNREACHABLE_RETRY_MS;
  let res: Response;
  for (;;) {
    try {
      res = await fetch(`${API_BASE}${path}`, {
        headers: { accept: 'application/json', ...extra },
        signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
        ...(mode === 'no-store' ? { cache: 'no-store' as const } : { next: { revalidate: seconds } }),
      });
      break;
    } catch (e) {
      // undici's "fetch failed" (TypeError) is a connection that never opened; a timeout is a DOMException and is not retried
      if (!(e instanceof TypeError) || Date.now() + UNREACHABLE_PAUSE_MS > until) throw e;
      await new Promise((r) => setTimeout(r, UNREACHABLE_PAUSE_MS));
    }
  }
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
export async function withLastGood<T extends object>(
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

/** The words of a topic code that name a subject (not the programme, the year or the kind of action) and the source's keywords, folded. */
const NOT_SUBJECT = new Set(['HORIZON', 'DIGITAL', 'EDF', 'EDIP', 'USI', 'DEPLOY', 'CSA', 'RIA', 'IRA', 'CPA', 'FNLC', 'JU', 'OPEN', 'TOPIC']);
function subjectWords(c: Pick<Call, 'topicId' | 'scope'>): Set<string> {
  const code = c.topicId.toUpperCase().split(/[^A-Z]+/).filter((w) => w.length >= 3 && !NOT_SUBJECT.has(w));
  return new Set([...code, ...c.scope.map((s) => s.trim().toLowerCase()).filter(Boolean)]);
}

/** The related calls of a call, from the open calls: the same subject first, then the same programme, then the same funder country. */
export function relatedCallsFrom(call: Call, open: Call[]): Call[] {
  const others = open.filter((c) => c.id !== call.id);
  // WP-109 (p05: the related calls of a cyber topic were AI chips): the calls that share the subject first, by the parts of the topic
  // code (CYBER, ECCC, CL3...) and the source's keywords; the programme and the country only after them
  const mine = subjectWords(call);
  const shared = (c: Call) => [...subjectWords(c)].filter((w) => mine.has(w)).length;
  const score = (c: Call) => 4 * shared(c) + (c.programme === call.programme ? 2 : 0) + (c.funderCountry === call.funderCountry ? 1 : 0);
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
  p.delete(PARAM.size);                 // WP-90: the address's name of the page size; the API reads pageSize
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
      for (const k of ['scope', 'sort', 'page', PARAM.size]) p.delete(k);
      if (filters.valueMin !== undefined || filters.valueMax !== undefined) p.set(PARAM.min, String(Math.max(filters.valueMin ?? 0, PLACEHOLDER_AMOUNT_MAX + 0.01)));
      const q = p.toString();
      return await http<ScopeCounts>(`/v1/tenders/scope-counts${q ? `?${q}` : ''}`, q === '' ? 'revalidate' : 'no-store', LIST_REVALIDATE_SECONDS);
    }
    const all = tenderMock.queryTenders({ ...filters, scope: 'all', page: 1, pageSize: 100000 }).items;
    const core = all.filter((t) => t.scope === 'core').length;
    const supply = all.filter((t) => t.scope === 'supply').length;
    return { relevant: core + supply, core, supply, overlap: 0, capped: false, asOf: now().toISOString() };
  } catch {
    return null;
  }
}

/**
 * Every open notice that states a deadline, for the deadline calendar (GET /v1/tenders/calendar, up to 3,000, soonest
 * first). It replaces five pages of the list, which held the 500 earliest of 1,529 (UX audit T9).
 */
export async function getTenderCalendar(filters: TenderFilters = {}): Promise<CalendarPage> {
  // WP-87: the tender list's own filters, as the list sends them (status, sort and page are not the calendar's)
  const query = toTenderQuery({ ...filters, status: undefined, sort: undefined, page: undefined, pageSize: undefined, buyer: undefined });
  if (API_BASE) {
    const path = `/v1/tenders/calendar${query}`;
    return withLastGood(`calendar:${path}`, () => httpOrThrow<CalendarPage>(path, 'revalidate', LIST_REVALIDATE_SECONDS), { persist: query === '' });
  }
  return tenderMock.queryCalendar(now(), filters);
}

/**
 * One page of a tenders CSV export: the notices of the same filters, newest first, `limit` at a time (the API
 * allows 2,000), with no total. `nextCursor` goes back as `cursor` until it is null. Always read live.
 */
export async function getTenderExportPage(
  filters: TenderFilters, cursor: string | null, limit: number, published: { publishedFrom?: string; publishedTo?: string } = {},
): Promise<{ items: Tender[]; nextCursor: string | null }> {
  if (API_BASE) {
    const p = new URLSearchParams(tendersQuery(filters));
    for (const k of ['page', 'pageSize', 'sort']) p.delete(k);
    p.set('limit', String(limit));
    if (cursor) p.set('cursor', cursor);
    // WP-100: by publication date (the API reads the notice date where none is stated)
    if (published.publishedFrom) p.set('publishedFrom', published.publishedFrom);
    if (published.publishedTo) p.set('publishedTo', published.publishedTo);
    return httpOrThrow<{ items: Tender[]; nextCursor: string | null }>(`/v1/tenders/export?${p.toString()}`, 'no-store');
  }
  // The demo build: the cursor is a row offset (a part of a file can be any size), the dates as the API reads them.
  const inRange = (t: Tender) => {
    const day = (t.publishedAt ?? t.noticeDate ?? '').slice(0, 10);
    return (!published.publishedFrom || (day !== '' && day >= published.publishedFrom)) && (!published.publishedTo || (day !== '' && day <= published.publishedTo));
  };
  const all = tenderMock.queryTenders({ ...filters, page: 1, pageSize: 100_000 }).items.filter(inRange);
  const at = cursor ? Number(cursor) : 0;
  return { items: all.slice(at, at + limit), nextCursor: at + limit < all.length ? String(at + limit) : null };
}

/** `slug` is "<id>-<words>"; the API looks up the leading id only. Callers redirect when the returned slug differs. */
export async function getTender(slug: string): Promise<Tender | null> {
  if (!isTenderSlug(slug)) return null;
  if (API_BASE) return http<Tender>(`/v1/tenders/${encodeURIComponent(slug)}`, 'revalidate', DETAIL_REVALIDATE_SECONDS);
  return tenderMock.findTender(slug);
}

/**
 * WP-121 (p10: an address cited in an earlier round answered 404): where an old notice address leads when `getTender` has none: the slug of
 * the same procurement's publication in scope, or the notice that left the defence scope (`left`). null for an id never held.
 */
export interface TenderMoved { slug: string | null; left: { title: string; noticeId: string; sourceName: string; url: string | null } | null }
export async function getTenderMoved(slug: string): Promise<TenderMoved | null> {
  if (!isTenderSlug(slug)) return null;
  if (API_BASE) return http<TenderMoved>(`/v1/tenders/${encodeURIComponent(slug)}/moved`, 'revalidate', DETAIL_REVALIDATE_SECONDS);
  return tenderMock.movedTender(slug);
}

/** The archive of one notice, newest first. */
export async function getTenderVersions(slug: string): Promise<TenderVersion[]> {
  if (!isTenderSlug(slug)) return [];
  if (API_BASE) return (await http<TenderVersion[]>(`/v1/tenders/${encodeURIComponent(slug)}/versions`, 'revalidate', DETAIL_REVALIDATE_SECONDS)) ?? [];
  return tenderMock.tenderVersions(slug) ?? [];
}

/** Slugs for the sitemap (open and last 12 months, core scope, at most 5,000). */
/**
 * WP-114: one page of the sitemap's tenders (GET /v1/tenders/sitemap): the core notices of one id range, every status;
 * `pages` is how many ranges there are. Kept an hour, as the sitemap.
 */
export async function getTenderSitemapPage(page: number): Promise<{ page: number; pages: number; items: { slug: string; updatedAt: string }[] }> {
  if (API_BASE) return httpOrThrow(`/v1/tenders/sitemap?page=${page}`, 'revalidate', SITEMAP_REVALIDATE_SECONDS);
  return { page, pages: 1, items: page === 0 ? await getAllTenderSlugs() : [] };
}

/** WP-114: every supplier that has a page, with the slug it answers under (GET /v1/suppliers/slugs). */
export async function getAllSupplierSlugs(): Promise<{ slug: string; updatedAt: string }[]> {
  if (API_BASE) return httpOrThrow<{ slug: string; updatedAt: string }[]>('/v1/suppliers/slugs', 'revalidate', SITEMAP_REVALIDATE_SECONDS);
  return supplierMock.querySuppliers({ pageSize: 100 } as Parameters<typeof supplierMock.querySuppliers>[0]).items
    .map((s) => ({ slug: s.slug, updatedAt: `${s.lastYear}-01-01T00:00:00Z` }));
}

export const SITEMAP_REVALIDATE_SECONDS = 3600;

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
  // Like the API: a week outside the archive, or not yet ended, is not there.
  if (filters.week && !tenderMock.weekAvailable(filters.week)) return null;
  return tenderMock.queryChanges(filters);
}

/**
 * WP-100: a page of the Atom feed holds this many entries, the newest first: two of the API's largest pages (200), read
 * at once. The whole window in one feed was 12 requests one after the other, 12.5 s and 1.37 MB for 2,403 entries (persona
 * round of 23 October 2026, p09); the older entries are on the feed's next page (RFC 5005 `rel="next"`).
 */
export const FEED_PAGE_SIZE = 200;
/** The number the subscribe block says (lib/analyst.ts), so the two cannot drift apart. */
export const FEED_PAGE_ENTRIES = FEED_MAX;
const FEED_API_PAGES = FEED_PAGE_ENTRIES / FEED_PAGE_SIZE;
/** The API serves 100 pages of a change list: the feed has at most this many pages. */
export const FEED_MAX_PAGE = Math.floor(100 / FEED_API_PAGES);
type FeedPage = ChangePage & { held: number; feedPage: number; feedPages: number };
// Fresh for five minutes (as the API keeps its answer); after that a reader is served the last page built, up to 30
// minutes old, while it is built again: the data changes once or twice a day, and a feed reader is never kept waiting.
const feedCache = new TtlCache<FeedPage>(5 * 60_000, 40);
const feedStale = new TtlCache<FeedPage>(30 * 60_000, 40);
const feedBuilding = new Map<string, Promise<FeedPage | null>>();

async function buildFeedPage(filters: ChangeFilters, page: number, key: string): Promise<FeedPage | null> {
  const apiPages = Array.from({ length: FEED_API_PAGES }, (_, i) => (page - 1) * FEED_API_PAGES + 1 + i);
  const got = await Promise.all(apiPages.map((p) => getChanges({ ...filters, page: p, pageSize: FEED_PAGE_SIZE })));
  const [first] = got;
  if (!first) return null;
  // A page that fails fails the feed: a feed silently cut short is worse than one the reader fetches again.
  if (got.some((g) => !g)) throw new ApiError(404, 'GET /v1/changes returned 404 for a page of the feed');
  // Pages read a moment apart can overlap when the window moved between them: an entry is in the feed once.
  const seen = new Set<string>();
  const items = got.flatMap((g) => g!.items).filter((c) => !seen.has(c.id) && seen.add(c.id));
  const built = { ...first, items, held: items.length, feedPage: page, feedPages: Math.min(FEED_MAX_PAGE, Math.max(1, Math.ceil(first.total / FEED_PAGE_ENTRIES))) };
  feedCache.set(key, built);
  feedStale.set(key, built);
  // WP-98c: the unfiltered feed's pages are also kept on disk, so a restarted server (a deploy) has a page to serve while it
  // builds the first one, and a build that fails serves the last one instead of a 502
  if (key.startsWith('#')) void remember(`feed:${key}`, built, { persist: true });
  return built;
}

/**
 * One page of the change window for the Atom feed (page 1: the newest FEED_PAGE_ENTRIES). `total` is the whole window,
 * `held` how many entries this page holds, `feedPages` how many pages the window fills. Built once at a time per query.
 */
export async function getChangesForFeed(filters: ChangeFilters, page = 1): Promise<FeedPage | null> {
  const key = `${toChangeQuery({ ...filters, page: 1 })}#${page}`;
  const hit = feedCache.get(key);
  if (hit) return hit;
  let building = feedBuilding.get(key);
  if (!building) {
    building = buildFeedPage(filters, page, key).finally(() => feedBuilding.delete(key));
    feedBuilding.set(key, building);
  }
  const stale = feedStale.get(key) ?? (await recall<FeedPage>(`feed:${key}`))?.value;
  if (stale) {
    building.catch(() => undefined);
    return stale;
  }
  return building;
}

/**
 * One issue of the weekly digest (GET /v1/digest): `week` is YYYY-Www, absent for the latest complete week. An issue
 * does not change once its week has ended, so the site shares one cached answer per week and country. null: no such
 * issue (a week outside the archive, or not ended) or an API build that does not have the endpoint.
 */
export async function getDigest(week?: string, country?: string, cpv?: string[]): Promise<Digest | null> {
  if (!API_BASE) return null;
  const p = new URLSearchParams();
  if (week) p.set('week', week);
  if (country) p.set('country', country);
  // WP-106: the tender sections narrowed to CPV prefixes
  if (cpv?.length) p.set('cpv', cpv.join(','));
  const path = `/v1/digest${p.size > 0 ? `?${p.toString()}` : ''}`;
  const got = await withLastGood(`digest:${path}`, async () => (await http<Digest>(path, 'revalidate', LIST_REVALIDATE_SECONDS)) ?? NO_ENDPOINT, { persist: !country && !cpv?.length });
  return got === NO_ENDPOINT ? null : (got as Digest);
}

/** The issues there are, newest first, with the counts of the stored ones (GET /v1/digest/weeks). Empty when unavailable. */
export async function getDigestWeeks(limit = 52): Promise<DigestWeek[]> {
  if (!API_BASE) return [];
  return (await http<DigestWeek[]>(`/v1/digest/weeks?limit=${limit}`, 'revalidate', LIST_REVALIDATE_SECONDS)) ?? [];
}

function buyersQuery(f: BuyerFilters): string {
  const p = new URLSearchParams(toBuyerQuery(f));
  // WP-98b: the order by the codes is the page's default with a CPV filter (so not in its address), never the API's
  if (f.sort === 'cpv') p.set('sort', 'cpv');
  p.set('pageSize', String(f.pageSize ?? BUYER_PAGE_SIZE));
  return `?${p.toString()}`;
}

/** `cpvCountCollapsed` (WP-98b): false when the counts under the codes are the plain ones (a notice and its copy may count twice). */
export async function getBuyers(filters: BuyerFilters = {}): Promise<Paginated<Buyer> & { staleAsOf?: string; cpvCountCollapsed?: boolean }> {
  if (API_BASE) {
    // The last good answer when the service does not answer (re-audit of 20 Oct, N2: /buyers?country=DE failed under light load).
    const shared = toBuyerQuery(filters) === '';
    const path = `/v1/buyers${buyersQuery(filters)}`;
    return withLastGood(`buyers:${path}`, () => httpOrThrow<Paginated<Buyer> & { cpvCountCollapsed?: boolean }>(path, shared ? 'revalidate' : 'no-store', LIST_REVALIDATE_SECONDS), { persist: shared });
  }
  return tenderMock.queryBuyers(filters);
}

const SUPPLIER_PAGE_SIZE = 20;

/** The supplier map's list (GET /v1/suppliers). Without the API (a demo build) it is five invented companies (lib/mock/suppliers.ts). */
export async function getSuppliers(f: SupplierFilters = {}): Promise<Paginated<SupplierItem> & { staleAsOf?: string; valuesAsOf?: string | null; valuesBehind?: boolean; groupTotals?: ValueSum[] | null; placsp?: boolean | null }> {
  if (!API_BASE) {
    // Like the API (backend/dgate/suppliers.py): a group it does not know is refused with 422. In the demo a group is a name prefix.
    if (f.group && supplierMock.querySuppliers({ group: f.group }).total === 0) throw new ApiError(422, 'group: unknown');
    return supplierMock.querySuppliers({ ...f, pageSize: f.pageSize ?? SUPPLIER_PAGE_SIZE });
  }
  const p = new URLSearchParams();
  if (f.q) p.set('q', f.q);
  if (f.country) p.set('country', f.country);
  if (f.buyerCountry) p.set('buyerCountry', f.buyerCountry);
  if (f.cpv) p.set('cpv', f.cpv);
  if (f.group) p.set('group', f.group);
  if (f.source) p.set('source', f.source);
  if (f.sort && f.sort !== 'awards') p.set('sort', f.sort);
  if (f.page && f.page > 1) p.set('page', String(f.page));
  const filtered = p.size > 0;
  p.set('pageSize', String(f.pageSize ?? SUPPLIER_PAGE_SIZE));
  const path = `/v1/suppliers?${p.toString()}`;
  return withLastGood(`suppliers:${path}`, () => httpOrThrow<Paginated<SupplierItem> & { valuesAsOf?: string | null; valuesBehind?: boolean; groupTotals?: ValueSum[] | null; placsp?: boolean | null }>(path, filtered ? 'no-store' : 'revalidate', LIST_REVALIDATE_SECONDS), { persist: !filtered });
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

/** `under` (WP-89): the CPV codes and buyer countries of the supplier report's link; the answer then counts the contracts under them. */
export async function getSupplier(slug: string, under: { cpv?: string; buyerCountry?: string } = {}): Promise<Supplier | null> {
  if (!isSupplierSlug(slug)) return null;
  if (!API_BASE) return supplierMock.findSupplier(slug, under);
  const p = new URLSearchParams();
  if (under.cpv) p.set('cpv', under.cpv);
  if (under.cpv && under.buyerCountry) p.set('buyerCountry', under.buyerCountry);
  const q = p.toString();
  return http<Supplier>(`/v1/suppliers/${encodeURIComponent(slug)}${q ? `?${q}` : ''}`, q ? 'no-store' : 'revalidate', DETAIL_REVALIDATE_SECONDS);
}

/** WP-100: every contract of a supplier, for its CSV (GET /v1/suppliers/{slug}/contracts). null: no such supplier; a 410 throws (`whenRemoved`). */
export async function getSupplierContracts(slug: string): Promise<SupplierContracts | null> {
  if (!isSupplierSlug(slug)) return null;
  if (!API_BASE) return supplierMock.supplierContracts(slug);
  return http<SupplierContracts>(`/v1/suppliers/${encodeURIComponent(slug)}/contracts`, 'no-store');
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
  if (filters.cpv?.length) p.set('cpv', filters.cpv.join(','));
  if (filters.scope) p.set('scope', filters.scope);
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

/** WP-90: who won this buyer's contracts (GET /v1/buyers/{slug}/suppliers). null when the API cannot answer: the page renders without it. */
/** WP-111: the buyer's top suppliers could not be read now (a timeout, a refusal under load): the page says so instead of leaving the table out. */
export const UNAVAILABLE = 'unavailable' as const;
export async function getBuyerSuppliers(buyer: Buyer, cpv?: string[]): Promise<BuyerSuppliers | typeof UNAVAILABLE | null> {
  if (!isBuyerSlug(buyer.slug)) return null;
  if (!API_BASE) return supplierMock.buyerSuppliers(buyer, cpv);
  // WP-105: under the page's CPV filter, as its tenders are (a filtered answer is not kept by the site)
  const q = cpv?.length ? `?cpv=${encodeURIComponent(cpv.join(','))}` : '';
  try {
    return await http<BuyerSuppliers>(`/v1/buyers/${encodeURIComponent(buyer.slug)}/suppliers${q}`, q ? 'no-store' : 'revalidate', DETAIL_REVALIDATE_SECONDS);
  } catch {
    return UNAVAILABLE;
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
