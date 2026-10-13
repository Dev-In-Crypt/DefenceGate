/**
 * CSV export of the public fields of a /tenders or /funding result. Used by the two `export.csv` route
 * handlers. Same filters as the list pages (lib/filters.ts parsers), data only through lib/api.ts.
 */
import { ApiError, getCalls, getTenders, isCallSlug, isTenderSlug } from './api';
import { getCallDeadline } from './deadline';
import { parseCallFilters, parseTenderFilters, toQuery, toTenderQuery, type SearchParams } from './filters';
import {
  EXPORT_CACHE_MAX, EXPORT_CACHE_TTL_MS, EXPORT_MAX_RUNNING, EXPORT_RETRY_AFTER_SECONDS, ExportRunner, Gate, TtlCache, exportCap,
} from './export-cache';
import { safeHttpUrl } from './safe-url';
import { absoluteUrl } from './seo';
import { anomalyNotes, tenderStatusView, valueKindLabel } from './tender-status';
import type { Call, Paginated, Tender } from './types';
import { isMidnight, isoUtc, toCsv, type Cell } from './csv';

/** The most rows one download holds (`status=all` holds at most 1,000: see export-cache.ts). */
export const EXPORT_CAP = 2000;
/** The API evaluates the whole filtered set once per page, so fewer, larger pages (its limit is 250). */
const TENDER_PAGE = 250;
const CALL_PAGE = 500;
const PARALLEL = 4;
const RETRIES = 4;


export const TENDER_HEADER = [
  'id', 'notice_id', 'title', 'buyer', 'country', 'cpv', 'procedure', 'published', 'deadline_utc', 'value', 'currency',
  'value_kind', 'status', 'notes', 'source_name', 'source_url', 'licence', 'attribution', 'retrieved_at_utc', 'page_url',
];

export function tenderRow(t: Tender): Cell[] {
  const dl = t.deadline;
  const dateOnly = dl !== null && (t.deadlineIsDate ?? isMidnight(dl));
  return [
    t.id, t.noticeId, t.title, t.buyerName, t.country, (t.cpvCodes?.length ? t.cpvCodes : t.cpv ? [t.cpv] : []).join(' '), t.procedure,
    isoUtc(t.publishedAt, t.publishedAt !== null && isMidnight(t.publishedAt)), isoUtc(dl, dateOnly),
    t.estimatedValue?.amount, t.estimatedValue?.currency, valueKindLabel(t.valueKind),
    tenderStatusView(t).word, anomalyNotes(t).join(' | '),
    t.source.sourceName, safeHttpUrl(t.source.url) ?? '', t.source.licence, t.source.attribution, isoUtc(t.source.retrievedAt),
    isTenderSlug(t.slug) ? absoluteUrl(`/tenders/${t.slug}`) : '',
  ];
}

export const CALL_HEADER = [
  'id', 'title', 'funder', 'country', 'programme', 'call_id', 'topic_id', 'action_type', 'opening_date', 'deadline_utc',
  'value', 'currency', 'status', 'source_name', 'source_url', 'licence', 'attribution', 'retrieved_at_utc', 'page_url',
];

export function callRow(c: Call): Cell[] {
  const dl = c.deadline;
  const status = c.status === 'forthcoming' ? 'Opens soon' : getCallDeadline(c).state === 'closed' ? 'Closed' : 'Open';
  return [
    c.id, c.title, c.issuer ?? c.programmeName, c.funderCountry, c.programmeName, c.callId, c.topicId, c.actionType,
    isoUtc(c.openingDate, c.openingDate !== null && isMidnight(c.openingDate)), isoUtc(dl, dl !== null && isMidnight(dl)),
    c.budget?.amount, c.budget?.currency, status,
    c.source.sourceName, safeHttpUrl(c.source.url) ?? '', c.source.licence, c.source.attribution, isoUtc(c.source.retrievedAt),
    isCallSlug(c.slug) ? absoluteUrl(`/funding/${c.slug}`) : '',
  ];
}

/** A URL's query as the page `searchParams` shape (a repeated key becomes a list). */
export function searchParamsOf(url: URL): SearchParams {
  const out: Record<string, string | string[]> = {};
  for (const k of new Set(url.searchParams.keys())) {
    const all = url.searchParams.getAll(k);
    out[k] = all.length === 1 ? all[0] : all;
  }
  return out;
}

/** A deep page of a broad query can time out at the API (503) or hit its limiter (429): try again a little later. */
async function withRetry<T>(run: () => Promise<T>): Promise<T> {
  for (let attempt = 1; ; attempt++) {
    try {
      return await run();
    } catch (err) {
      const retryable = err instanceof ApiError && (err.status === 503 || err.status === 429 || err.status === 502);
      if (!retryable || attempt >= RETRIES) throw err;
      await new Promise((r) => setTimeout(r, 600 * attempt));
    }
  }
}

/** Page 1, then the rest four at a time, up to `cap` rows. A page that cannot be had fails the export. */
async function collect<T extends { id: string }>(fetchOne: (page: number) => Promise<Paginated<T>>, cap: number): Promise<{ items: T[]; total: number }> {
  const fetchPage = (page: number) => withRetry(() => fetchOne(page));
  const first = await fetchPage(1);
  const items = [...first.items];
  const size = Math.max(1, first.pageSize || first.items.length || 1);
  const pages = Math.ceil(Math.min(first.total, cap) / size);
  for (let p = 2; p <= pages; p += PARALLEL) {
    const batch = Array.from({ length: Math.min(PARALLEL, pages - p + 1) }, (_, i) => fetchPage(p + i));
    for (const r of await Promise.all(batch)) items.push(...r.items);
  }
  // The pages are read a moment apart: a notice that arrives between two reads shifts the boundary
  // and would appear on both. Each row is listed once.
  const seen = new Set<string>();
  const once = items.filter((t) => (seen.has(t.id) ? false : (seen.add(t.id), true)));
  return { items: once.slice(0, cap), total: first.total };
}

interface Built { body: string; total: number; rows: number; cap: number }

/**
 * A built export is kept for ten minutes (30 at most, by normalised query: the parsed filters with defaults left
 * out), identical requests in flight share one build, and a seventh uncached build at once is refused.
 */
const runner = new ExportRunner<Built>(new TtlCache(EXPORT_CACHE_TTL_MS, EXPORT_CACHE_MAX), new Gate(EXPORT_MAX_RUNNING));

const busy = () => new Response('Too many exports are running at the moment. Try again in a few seconds.', {
  status: 429,
  headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store', 'retry-after': String(EXPORT_RETRY_AFTER_SECONDS) },
});

const stamp = () => new Date().toISOString().slice(0, 10);

function csvResponse(b: Built, name: string): Response {
  return new Response(b.body, {
    headers: {
      'content-type': 'text/csv; charset=utf-8',
      'content-disposition': `attachment; filename="${name}-${stamp()}.csv"`,
      'cache-control': 'public, max-age=300',
      'x-total-matching': String(b.total),
      'x-rows': String(b.rows),
      'x-row-cap': String(b.cap),
    },
  });
}

const unavailable = () => new Response('The data service is not available. Try again in a few minutes.', {
  status: 502, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
});

export async function tendersCsvResponse(url: URL): Promise<Response> {
  const parsed = parseTenderFilters(searchParamsOf(url));
  const filters = { ...parsed, pageSize: TENDER_PAGE };
  const cap = exportCap(parsed.status, EXPORT_CAP);
  try {
    const r = await runner.get(`tenders${toTenderQuery({ ...parsed, page: 1 })}`, async () => {
      const { items, total } = await collect((page) => getTenders({ ...filters, page }, { fresh: true }), cap);
      return { body: toCsv(TENDER_HEADER, items.map(tenderRow)), total, rows: items.length, cap };
    });
    return 'busy' in r ? busy() : csvResponse(r.value, 'defencegate-tenders');
  } catch (err) {
    console.error('tenders csv export failed:', err instanceof Error ? err.message : String(err));
    return unavailable();
  }
}

export async function callsCsvResponse(url: URL): Promise<Response> {
  const parsed = parseCallFilters(searchParamsOf(url));
  const filters = { ...parsed, pageSize: CALL_PAGE };
  const cap = exportCap(parsed.status, EXPORT_CAP);
  try {
    const r = await runner.get(`funding${toQuery({ ...parsed, page: 1 })}`, async () => {
      const { items, total } = await collect((page) => getCalls({ ...filters, page }, { fresh: true }), cap);
      return { body: toCsv(CALL_HEADER, items.map(callRow)), total, rows: items.length, cap };
    });
    return 'busy' in r ? busy() : csvResponse(r.value, 'defencegate-funding');
  } catch (err) {
    console.error('funding csv export failed:', err instanceof Error ? err.message : String(err));
    return unavailable();
  }
}
