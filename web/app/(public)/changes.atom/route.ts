import { getChangesForFeed } from '@/lib/api';
import { buildAtom, etagOf, feedSubtitle } from '@/lib/atom';
import { parseChangeFilters, toChangeQuery } from '@/lib/filters';
import { searchParamsOf } from '@/lib/export';
import { SITE } from '@/lib/seo';

/**
 * What changed in the last 14 days, as an Atom feed: new notices and real amendments (deadline, value, status,
 * procedure), one entry per notice per day. `country` and `scope` narrow it like the page. It holds the whole window as
 * far as the API gives it (lib/api.ts getChangesForFeed reads it page by page, up to FEED_MAX_ENTRIES; the subtitle says so
 * only when that cap cuts it; it was the newest 100 of 2,311). It answers conditional requests (ETag and Last-Modified)
 * and is kept five minutes, as the API keeps its answer. A digest week or a kind in the address is not a feed: it is dropped.
 */
export async function GET(request: Request): Promise<Response> {
  const { week: _week, kind: _kind, ...asked } = parseChangeFilters(searchParamsOf(new URL(request.url)));
  const filters = { ...asked, page: 1 };
  const data = await getChangesForFeed(filters).catch(() => null);
  if (!data) {
    return new Response('The change feed could not be built right now. Try again in a few minutes.', {
      status: 502, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  const query = toChangeQuery({ country: filters.country, scope: filters.scope });
  // Funding calls (new, or a date moved) travel in the same feed under their own categories; only the unfiltered
  // by-scope view carries them, as in the API.
  const funding = data.funding ?? [];
  const body = buildAtom(data.items, {
    origin: SITE.url.replace(/\/$/, ''),
    selfPath: `/changes.atom${query}`,
    pagePath: `/changes${query}`,
    title: 'DefenceGate: what changed',
    subtitle: feedSubtitle(data.windowDays, data.total, data.held),
    generatedAt: data.windowTo,
  }, funding);
  const lastModified = new Date([...data.items, ...funding].reduce((m, c) => (c.detectedAt > m ? c.detectedAt : m), data.windowFrom));
  const etag = etagOf(body);
  const headers = {
    etag,
    'last-modified': lastModified.toUTCString(),
    'cache-control': 'public, max-age=300',
  };
  const sent = request.headers.get('if-none-match');
  const since = request.headers.get('if-modified-since');
  const notModified = sent !== null
    ? sent.split(',').some((t) => t.trim() === etag || t.trim() === `W/${etag}`)
    : since !== null && !Number.isNaN(Date.parse(since)) && Date.parse(since) >= lastModified.getTime();
  if (notModified) return new Response(null, { status: 304, headers });
  return new Response(body, { headers: { ...headers, 'content-type': 'application/atom+xml; charset=utf-8' } });
}
