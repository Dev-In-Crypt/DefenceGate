import { getChanges } from '@/lib/api';
import { buildAtom, etagOf } from '@/lib/atom';
import { parseChangeFilters, toChangeQuery } from '@/lib/filters';
import { searchParamsOf } from '@/lib/export';
import { SITE } from '@/lib/seo';

/** The newest entries a reader gets: the API keeps 14 days and this is its cached page size. */
const FEED_ENTRIES = 100;

/**
 * What changed in the last 14 days, as an Atom feed: new notices and real amendments (deadline, value, status,
 * procedure), one entry per notice per day. `country` and `scope` narrow it like the page. It answers conditional
 * requests (ETag and Last-Modified) and is kept five minutes, as the API keeps its answer.
 */
export async function GET(request: Request): Promise<Response> {
  const filters = { ...parseChangeFilters(searchParamsOf(new URL(request.url))), page: 1, pageSize: FEED_ENTRIES };
  const data = await getChanges(filters).catch(() => null);
  if (!data) {
    return new Response('The change feed could not be built right now. Try again in a few minutes.', {
      status: 502, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  const query = toChangeQuery({ country: filters.country, scope: filters.scope });
  const body = buildAtom(data.items, {
    origin: SITE.url.replace(/\/$/, ''),
    selfPath: `/changes.atom${query}`,
    pagePath: `/changes${query}`,
    title: 'DefenceGate: what changed',
    subtitle: `New defence and dual-use notices and amendments to their deadline, value, status or procedure, from the last ${data.windowDays} days. Our archive began in September 2026.`,
    generatedAt: data.windowTo,
  });
  const lastModified = new Date(data.items.reduce((m, c) => (c.detectedAt > m ? c.detectedAt : m), data.windowFrom));
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
