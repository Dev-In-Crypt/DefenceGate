/**
 * CSV export of the public fields of a /tenders or /funding result. Used by the two `export.csv` route
 * handlers. Same filters as the list pages (lib/filters.ts parsers), data only through lib/api.ts.
 */
import { ApiError, REMOVED, getCalls, getHealth, getMarketStats, getSupplierContracts, getTenderExportPage, isCallSlug, isTenderSlug, whenRemoved } from './api';
import { callStatusKind, getCallDeadline } from './deadline';
import { CALL_EXPORT_PARAMS, TENDER_EXPORT_PARAMS, WHO_BADGE, parseCallFilters, parseMarketFilters, parseTenderFilters, toQuery, toTenderQuery, unknownParams, type SearchParams } from './filters';
import { programmeNameOf } from './funding-feed';
import { REGIMES } from './taxonomy';
import { MARKET_HEADER, SUPPLIER_CONTRACT_HEADER, VALUE_KIND_NOT_STATED, csvValueKind, marketRows, supplierContractRows, winnerCells } from './export-tables';
import {
  EXPORT_CACHE_MAX, EXPORT_CACHE_TTL_MS, EXPORT_MAX_RUNNING, EXPORT_PAGE_MIN, EXPORT_PER_CLIENT, EXPORT_RETRY_AFTER_SECONDS, ExportRunner, Gate,
  TtlCache, collectByCursor, exportCap, listOrder, tooBroad,
} from './export-cache';
import { clientIp } from './hits';
import { safeHttpUrl } from './safe-url';
import { absoluteUrl } from './seo';
import { anomalyNotes, tenderStatusView } from './tender-status';
import { basisChips, confidenceCell } from './tender-basis';
import type { Call, Paginated, Tender } from './types';
import { isMidnight, isoUtc, toCsv, truncationRow, type Cell } from './csv';
import { isPlaceholderAmount } from './format';

/** The most rows one download holds (`status=all` holds at most 1,000: see export-cache.ts). */
export const EXPORT_CAP = 2000;
const CALL_PAGE = 500;
const PARALLEL = 4;
const RETRIES = 4;


export const TENDER_HEADER = [
  'id', 'notice_id', 'title', 'buyer', 'country', 'cpv', 'procedure', 'published', 'deadline_utc', 'value', 'currency',
  'value_kind', 'status', 'notes', 'source_name', 'source_url', 'licence', 'attribution', 'archive_changed_at_utc', 'page_url',
  // WP-20: why the notice is on the list (scope and the reasons), how many versions the archive holds, and whether the
  // file holds the whole result. The last is a column and not a line in the data, so the file stays rectangular and
  // a parser needs no special case: `true` on every row when the result was cut at the row limit.
  'scope', 'why_listed', 'versions', 'result_truncated',
  // WP-23: how sure we are, the level only. Appended last, so the column order of the file never moves.
  'confidence',
  // WP-106 (p06, p07): who the award names, and their countries (`|` between winners). Appended last.
  'winners', 'winner_countries',
];

export function tenderRow(t: Tender, truncated = false): Cell[] {
  const dl = t.deadline;
  const dateOnly = dl !== null && (t.deadlineIsDate ?? isMidnight(dl));
  // A placeholder amount (0, 0.01, 1) is not a value: blank, so a sum is not poisoned. WP-106: an award's own value with its kind
  // (the page's "Awarded value" or "Framework ceiling"), else the notice's.
  const award = t.awardValue && !isPlaceholderAmount(t.awardValue.amount) ? { amount: t.awardValue.amount, currency: t.awardValue.currency } : null;
  const value = award ?? (t.estimatedValue && !isPlaceholderAmount(t.estimatedValue.amount) ? t.estimatedValue : null);
  return [
    t.id, t.noticeId, t.title, t.buyerName, t.country, (t.cpvCodes?.length ? t.cpvCodes : t.cpv ? [t.cpv] : []).join(' '), t.procedure,
    isoUtc(t.publishedAt, t.publishedAt !== null && isMidnight(t.publishedAt)), isoUtc(dl, dateOnly),
    // WP-108 (p07: empty on 24 rows, "not stated" on 57): one vocabulary, every row says its value kind; no value is "not stated"
    value?.amount, value?.currency, (value ? csvValueKind(award ? t : { ...t, awardValue: null }) : null) ?? VALUE_KIND_NOT_STATED,
    tenderStatusView(t).word, anomalyNotes(t).join(' | '),
    t.source.sourceName, safeHttpUrl(t.source.url) ?? '', t.source.licence, t.source.attribution, isoUtc(t.source.retrievedAt),
    isTenderSlug(t.slug) ? absoluteUrl(`/tenders/${t.slug}`) : '',
    t.scope, basisChips(t).join(' | '), t.versionCount, truncated ? 'true' : 'false',
    confidenceCell(t.confidence),
    ...winnerCells(t),
  ];
}

export const CALL_HEADER = [
  'id', 'title', 'funder', 'country', 'programme', 'call_id', 'topic_id', 'action_type', 'opening_date', 'deadline_utc',
  'value', 'currency', 'budget_scope', 'status', 'source_name', 'source_url', 'licence', 'attribution', 'retrieved_at_utc', 'page_url',
  // WP-109 (p09): what the list's filters and badges say, so a file can be filtered as the page is
  'who_may_apply', 'research_may_apply', 'regime', 'open_to_ukraine', 'min_consortium',
];

const tri = (v: boolean | null | undefined): string => (v === true ? 'yes' : v === false ? 'no' : 'not stated');

export function callRow(c: Call): Cell[] {
  const dl = c.deadline;
  // The same function the pages read, so the file and the page cannot say two things (site-qa2:N5).
  const kind = callStatusKind(c.status, getCallDeadline(c).state, c.openingDate);
  const status = kind === 'closed' ? 'Closed' : kind === 'upcoming' ? 'Opens soon' : kind === 'pending' ? 'Opening date passed' : 'Open';
  const budget = c.budget && !isPlaceholderAmount(c.budget.amount) ? c.budget : null;
  return [
    c.id, c.title, c.funder, c.funderCountry, programmeNameOf(c), c.callId, c.topicId, c.actionType,
    isoUtc(c.openingDate, c.openingDate !== null && isMidnight(c.openingDate)), isoUtc(dl, dl !== null && isMidnight(dl)),
    budget?.amount, budget?.currency, budget ? c.budgetScope : null, status,
    c.source.sourceName, safeHttpUrl(c.source.url) ?? '', c.source.licence, c.source.attribution, isoUtc(c.source.retrievedAt),
    isCallSlug(c.slug) ? absoluteUrl(`/funding/${c.slug}`) : '',
    c.whoMayApply ? WHO_BADGE[c.whoMayApply] : 'not stated', tri(c.researchMayApply), REGIMES[c.regime] ?? c.regime, tri(c.openToUkraine),
    c.eligibility.find((r) => r.label === 'Minimum consortium')?.value ?? '',
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

/**
 * A page that hits the API's limiter (429) or a restart (502) is tried again a little later. A 503 is the API
 * saying the query itself outran its time budget: asking again is five more seconds of database time for the
 * same answer, so it is not retried (audit X-3: four attempts burned about 20 s per failed export).
 */
async function withRetry<T>(run: () => Promise<T>): Promise<T> {
  for (let attempt = 1; ; attempt++) {
    try {
      return await run();
    } catch (err) {
      const retryable = err instanceof ApiError && (err.status === 429 || err.status === 502);
      if (!retryable || attempt >= RETRIES) throw err;
      await new Promise((r) => setTimeout(r, 600 * attempt));
    }
  }
}

/** What a page may fail with and still be worth asking again, smaller: the API's limiter, a restart, "too slow". */
const retryableStatus = (err: unknown) => err instanceof ApiError && [429, 502, 503].includes(err.status);

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

/** `total` is null when the file was cut: the export never counts the rest. `next`: the address of the next part (WP-100). */
interface Built { body: string; total: number | null; rows: number; cap: number; next?: string }

/**
 * A built export is kept for ten minutes (30 at most, by normalised query: the parsed filters with defaults left
 * out), identical requests in flight share one build, a seventh uncached build at once is refused, and so is a third
 * from one client (the visitor's address as Caddy set it).
 */
const runner = new ExportRunner<Built>(new TtlCache(EXPORT_CACHE_TTL_MS, EXPORT_CACHE_MAX), new Gate(EXPORT_MAX_RUNNING), EXPORT_PER_CLIENT);

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
      ...(b.total === null ? { 'x-truncated': 'true' } : { 'x-total-matching': String(b.total) }),
      'x-rows': String(b.rows),
      'x-row-cap': String(b.cap),
      // WP-100: the cap, in words, and where the rest is (RFC 8288)
      'x-row-cap-note': `At most ${b.cap.toLocaleString('en-GB')} rows a file${b.next ? '; this one was cut there and the next part is in the Link header' : ''}.`,
      ...(b.next ? { 'x-next-part': b.next, link: `<${b.next}>; rel="next"` } : {}),
    },
  });
}

const unavailable = () => new Response('The data service is not available. Try again in a few minutes.', {
  status: 502, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
});

const text = (status: number, body: string, extra: Record<string, string> = {}) => new Response(body, {
  status, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store', ...extra },
});

const NARROW = 'Narrow it with a country, a CPV code, a buyer, a search text or a date range, or leave the scope on its default.';

const tooWide = () => text(503, `This export could not be built within the time the data service allows, even in small pages. ${NARROW}`, { 'retry-after': '60' });

/** What a failed build says: the service's own "too slow" and "too many" are passed on, not turned into "not available". */
function failure(err: unknown): Response {
  if (err instanceof ApiError && err.status === 503) return tooWide();
  if (err instanceof ApiError && err.status === 429) return busy();
  return unavailable();
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/**
 * WP-100: what the tenders file reads beyond the list's filters: a publication-date range (`publishedFrom`, `publishedTo`,
 * inclusive days; the list has no such filter, so a time series is read a year at a time), and `cursor`, where the part
 * before stopped (a result longer than one file comes in parts: a cut file names the next in its `Link` and `x-next-part`
 * headers, and every row says `result_truncated = true`). A malformed value is a 400, never ignored.
 */
export function exportExtras(url: URL): { publishedFrom?: string; publishedTo?: string; cursor: string | null } | { bad: string } {
  const out: { publishedFrom?: string; publishedTo?: string; cursor: string | null } = { cursor: null };
  for (const k of ['publishedFrom', 'publishedTo'] as const) {
    const v = url.searchParams.get(k);
    if (v === null || v === '') continue;
    if (!DAY.test(v) || Number.isNaN(Date.parse(`${v}T00:00:00Z`))) return { bad: `${k}=${v} is not a day (use YYYY-MM-DD).` };
    out[k] = v;
  }
  const cursor = url.searchParams.get('cursor');
  if (cursor) {
    if (!/^\d{1,18}$/.test(cursor)) return { bad: `cursor=${cursor} is not a cursor of this export (take it from next_part_url).` };
    out.cursor = cursor;
  }
  return out;
}

/** The address of the next part: this file's own query with the cursor where it stopped. */
export function nextPartUrl(url: URL, cursor: string): string {
  const q = new URLSearchParams(url.searchParams);
  q.set('cursor', cursor);
  return absoluteUrl(`${url.pathname}?${q.toString()}`);
}

/** WP-114: a parameter a file does not read is a 422 naming it, as the Atom feeds answer; null when all are read. */
export function refuseUnknown(url: URL, known: readonly string[]): Response | null {
  const unknown = unknownParams(searchParamsOf(url), known);
  return unknown.length ? text(422, `${unknown.join('\n')}\nThis file reads: ${known.join(', ')}.`) : null;
}

export async function tendersCsvResponse(url: URL, forwardedFor: string | null = null): Promise<Response> {
  const refused = refuseUnknown(url, TENDER_EXPORT_PARAMS);
  if (refused) return refused;
  const parsed = parseTenderFilters(searchParamsOf(url));
  const extras = exportExtras(url);
  if ('bad' in extras) return text(400, extras.bad);
  const { cursor: from, ...published } = extras;
  if (tooBroad({ ...parsed, ...published })) return text(400, `This export would hold every notice of every status and scope. ${NARROW}`);
  const cap = exportCap(parsed.status, EXPORT_CAP);
  const key = new URLSearchParams(toTenderQuery({ ...parsed, page: 1 }));
  for (const [k, v] of Object.entries({ ...published, cursor: from ?? '' })) if (v) key.set(k, v);
  try {
    const r = await runner.get(`tenders?${key.toString()}`, async () => {
      // By cursor over the API's export endpoint (a keyed scan, no count): a page costs the same at any depth.
      const { items: read, more, cursor } = await collectByCursor(
        (c, size) => getTenderExportPage(parsed, c, size, published), cap, { retryable: retryableStatus, from });
      // The list's order (its `sort`, or its default) is applied to what was read. A result longer than the limit holds the
      // most recently added notices, in that order, and names the next part: the limit is by date added, not by the sort.
      const items = listOrder(read, parsed.status, parsed.sort, parsed.scope);
      const next = more && cursor ? nextPartUrl(url, cursor) : '';
      return {
        body: toCsv(TENDER_HEADER, items.map((t) => tenderRow(t, more))), total: more ? null : items.length, rows: items.length, cap,
        ...(next ? { next } : {}),
      };
    }, clientIp(forwardedFor));
    return 'busy' in r ? busy() : csvResponse(r.value, 'defencegate-tenders');
  } catch (err) {
    console.error('tenders csv export failed:', err instanceof Error ? err.message : String(err));
    return failure(err);
  }
}

/** WP-100: every contract of a supplier (its page lists the newest 50), with the tender file's attribution columns. */
export async function supplierContractsCsvResponse(slug: string): Promise<Response> {
  try {
    const got = await getSupplierContracts(slug).catch(whenRemoved);
    if (got === REMOVED) return text(410, 'This supplier was removed from DefenceGate on request.');
    if (!got) return text(404, 'There is no such supplier.');
    const cut = got.total > got.items.length;
    return csvResponse({
      body: toCsv(SUPPLIER_CONTRACT_HEADER, supplierContractRows(got, absoluteUrl)), total: cut ? null : got.total, rows: got.items.length, cap: got.cap,
    }, `defencegate-supplier-${got.slug}`);
  } catch (err) {
    console.error('supplier csv export failed:', err instanceof Error ? err.message : String(err));
    return failure(err);
  }
}

/** WP-100: the market page's tables (/market, the same year, country and CPV), one row per bar or table row. */
export async function marketCsvResponse(url: URL): Promise<Response> {
  const filters = parseMarketFilters(searchParamsOf(url));
  try {
    const [stats, health] = await Promise.all([getMarketStats(filters), getHealth().catch(() => null)]);
    if (!stats) return unavailable();
    const terms = new Map((health?.sources ?? []).map((s) => [s.id, { name: s.name, licence: s.licence, attribution: s.attribution }]));
    const q = new URLSearchParams();
    if (filters.year) q.set('year', String(filters.year));
    if (filters.country) q.set('country', filters.country);
    if (filters.cpv?.length) q.set('cpv', filters.cpv.join(','));
    if (filters.scope) q.set('scope', filters.scope);
    const rows = marketRows(stats, terms, absoluteUrl(`/market${q.size ? `?${q.toString()}` : ''}`));
    return csvResponse({ body: toCsv(MARKET_HEADER, rows), total: rows.length, rows: rows.length, cap: rows.length }, 'defencegate-market');
  } catch (err) {
    console.error('market csv export failed:', err instanceof Error ? err.message : String(err));
    return failure(err);
  }
}

export async function callsCsvResponse(url: URL, forwardedFor: string | null = null): Promise<Response> {
  const refused = refuseUnknown(url, CALL_EXPORT_PARAMS);
  if (refused) return refused;
  const parsed = parseCallFilters(searchParamsOf(url));
  const filters = { ...parsed, pageSize: CALL_PAGE };
  const cap = exportCap(parsed.status, EXPORT_CAP);
  try {
    const r = await runner.get(`funding${toQuery({ ...parsed, page: 1 })}`, async () => {
      const read = (size: number) => collect((page) => getCalls({ ...filters, page, pageSize: size }, { fresh: true }), cap);
      // "Too slow" is answered with a smaller page after a pause, once, before it is a failure.
      const { items, total } = await read(CALL_PAGE).catch(async (err: unknown) => {
        if (!retryableStatus(err)) throw err;
        await new Promise((res) => setTimeout(res, 1000));
        return read(EXPORT_PAGE_MIN);
      });
      const cut = truncationRow(CALL_HEADER.length, items.length, total, cap);
      return { body: toCsv(CALL_HEADER, [...items.map(callRow), ...(cut ? [cut] : [])]), total, rows: items.length, cap };
    }, clientIp(forwardedFor));
    return 'busy' in r ? busy() : csvResponse(r.value, 'defencegate-funding');
  } catch (err) {
    console.error('funding csv export failed:', err instanceof Error ? err.message : String(err));
    return failure(err);
  }
}
