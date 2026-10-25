import { ApiError, FEED_MAX_PAGE, FEED_PAGE_ENTRIES, getChangesForFeed } from '@/lib/api';
import { buildAtom, etagOf, feedSubtitle } from '@/lib/atom';
import { notModified } from '@/lib/etag';
import { searchSummary } from '@/lib/feed-name';
import { CHANGE_PARAMS, parseChangeFilters, toChangeQuery, unknownParams } from '@/lib/filters';
import { searchParamsOf } from '@/lib/export';
import { SITE } from '@/lib/seo';

/**
 * What changed in the last 14 days, as an Atom feed: new notices and real amendments (deadline, value, status,
 * procedure), one entry per notice per day. `country`, `scope` and the tender list's filters (q, cpv, deadline and value range:
 * WP-87) narrow it like the page; a parameter it does not read is a 422. WP-100: a paged feed (RFC 5005): `page` 1 (the
 * default) holds the newest FEED_PAGE_ENTRIES, `rel="next"` leads to the older ones, and the subtitle says how many there
 * are; the title names the search ("DefenceGate: radar, DE+PL"). It answers conditional requests (ETag and Last-Modified)
 * and is kept five minutes (lib/api.ts getChangesForFeed). A digest week or a kind in the address is not a feed: it is dropped.
 */
export async function GET(request: Request): Promise<Response> {
  const sp = searchParamsOf(new URL(request.url));
  // WP-87: a parameter the feed does not read is refused (a feed cannot show a notice), never dropped in silence
  const unknown = unknownParams(sp, CHANGE_PARAMS);
  if (unknown.length > 0) {
    return new Response(`${unknown.join('\n')}\nThe change feed reads: ${CHANGE_PARAMS.join(', ')}.`, {
      status: 422, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  const { week: _week, kind: _kind, page: asked = 1, pageSize: _size, ...filters } = parseChangeFilters(sp);
  // WP-114: a page past what the feed can ever hold is not an outage (page=999 answered 502: the API refuses page > 100)
  if (asked > FEED_MAX_PAGE) {
    return new Response(`This feed has at most ${FEED_MAX_PAGE} pages.`, {
      status: 404, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=300' },
    });
  }
  const data = await getChangesForFeed(filters, asked).catch((e: unknown) => (e instanceof ApiError && e.status === 422 ? 'refused' : null));
  if (data === 'refused') {
    return new Response('The change feed cannot read these filters.', {
      status: 422, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  if (!data) {
    return new Response('The change feed could not be built right now. Try again in a few minutes.', {
      status: 502, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  if (asked > data.feedPages) {
    return new Response(`This feed has ${data.feedPages} ${data.feedPages === 1 ? 'page' : 'pages'}.`, {
      status: 404, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=300' },
    });
  }
  // every filter the feed read (WP-87: the tender list's too), in its own address and in its page's
  const at = (page: number) => `/changes.atom${toChangeQuery({ ...filters, page })}`;
  const query = toChangeQuery(filters);
  // Funding calls (new, or a date moved) travel in the same feed under their own categories; only the unfiltered
  // by-scope view carries them, as in the API (page 1 only).
  const funding = data.funding ?? [];
  const search = searchSummary(filters);
  const body = buildAtom(data.items, {
    origin: SITE.url.replace(/\/$/, ''),
    selfPath: at(asked),
    pagePath: `/changes${query}`,
    title: search ? `DefenceGate: ${search}` : 'DefenceGate: what changed',
    subtitle: feedSubtitle(data.windowDays, data.total, data.held, { page: asked, pages: data.feedPages, size: FEED_PAGE_ENTRIES }, funding.length),
    generatedAt: data.windowTo,
    ...(data.feedPages > 1 ? { first: at(1) } : {}),
    ...(asked > 1 ? { prev: at(asked - 1) } : {}),
    ...(asked < data.feedPages ? { next: at(asked + 1) } : {}),
  }, funding);
  const lastModified = new Date([...data.items, ...funding].reduce((m, c) => (c.detectedAt > m ? c.detectedAt : m), data.windowFrom));
  const etag = etagOf(body);
  const headers = {
    etag,
    'last-modified': lastModified.toUTCString(),
    'cache-control': 'public, max-age=300',
  };
  // WP-120: If-Modified-Since at the header's whole second (the feed's own Last-Modified got 200 and the whole body)
  if (notModified(request, etag, lastModified)) return new Response(null, { status: 304, headers });
  return new Response(body, { headers: { ...headers, 'content-type': 'application/atom+xml; charset=utf-8' } });
}
