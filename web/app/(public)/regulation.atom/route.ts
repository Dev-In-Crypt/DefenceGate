import { etagOf } from '@/lib/atom';
import { getRegulation } from '@/lib/regulation-api';
import { buildRegulationAtom } from '@/lib/regulation';
import { SITE } from '@/lib/seo';

/**
 * The regulatory tracker as an Atom feed: one entry per tracker entry, newest event first. It changes when the
 * tracker is edited, so it answers conditional requests and is kept an hour.
 */
export async function GET(request: Request): Promise<Response> {
  const feed = await getRegulation().catch(() => null);
  if (!feed) {
    return new Response('The regulatory tracker could not be read right now. Try again in a few minutes.', {
      status: 502, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  const body = buildRegulationAtom(feed, { origin: SITE.url.replace(/\/$/, ''), generatedAt: new Date().toISOString() });
  const lastModified = new Date(`${feed.lastChecked ?? '1970-01-01'}T00:00:00Z`);
  const etag = etagOf(body);
  const headers = { etag, 'last-modified': lastModified.toUTCString(), 'cache-control': 'public, max-age=3600' };
  const sent = request.headers.get('if-none-match');
  const since = request.headers.get('if-modified-since');
  const notModified = sent !== null
    ? sent.split(',').some((t) => t.trim() === etag || t.trim() === `W/${etag}`)
    : since !== null && !Number.isNaN(Date.parse(since)) && Date.parse(since) >= lastModified.getTime();
  if (notModified) return new Response(null, { status: 304, headers });
  return new Response(body, { headers: { ...headers, 'content-type': 'application/atom+xml; charset=utf-8' } });
}
