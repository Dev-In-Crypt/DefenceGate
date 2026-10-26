import { getDigest, getDigestWeeks } from '@/lib/api';
import { etagOf } from '@/lib/atom';
import { notModified } from '@/lib/etag';
import { buildDigestAtom, parseDigestFilters, unknownDigestCountry } from '@/lib/digest';
import { searchParamsOf } from '@/lib/export';
import { SITE } from '@/lib/seo';
import type { Digest } from '@/lib/types';

/** The newest issues a reader gets: a month of weeks. */
const FEED_ISSUES = 4;

/**
 * The weekly digest as an Atom feed: one entry per issue (counts and the first headlines), newest first. `country`
 * narrows it like the page. An issue does not change once its week has ended, so the feed answers conditional requests
 * (ETag and Last-Modified) and is kept an hour.
 */
export async function GET(request: Request): Promise<Response> {
  const sp = searchParamsOf(new URL(request.url));
  // A feed that quietly returned every country for a mistyped one would mislead a subscriber.
  const unknown = unknownDigestCountry(sp);
  if (unknown) {
    return new Response(`Unknown country: ${unknown}. Use a two-letter code the digest page lists, or leave it out.`, {
      status: 400, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  const filters = parseDigestFilters(sp);
  const weeks = await getDigestWeeks(FEED_ISSUES).catch(() => null);
  if (!weeks) return unavailable();
  const got = await Promise.all(weeks.map((w) => getDigest(w.week, filters.country, filters.cpv).catch(() => null)));
  // Half a feed presented as the whole one would mislead a subscriber: an issue that cannot be read is an error.
  if (got.some((d) => d === null)) return unavailable();
  const issues = got as Digest[];
  const lastModified = new Date(issues.reduce((m, d) => (d.weekTo > m ? d.weekTo : m), '1970-01-01T00:00:00Z'));
  // WP-142: a feed with no issue is dated like its Last-Modified, never by the clock: `<updated>` at the second of the request gave
  // two requests a second apart two ETags, and a reader holding the first never got its 304 (the e2e flake of 26 October 2026)
  const body = buildDigestAtom(issues, { origin: SITE.url.replace(/\/$/, ''), country: filters.country, cpv: filters.cpv, generatedAt: lastModified.toISOString() });
  const etag = etagOf(body);
  const headers = { etag, 'last-modified': lastModified.toUTCString(), 'cache-control': 'public, max-age=3600' };
  if (notModified(request, etag, lastModified)) return new Response(null, { status: 304, headers });
  return new Response(body, { headers: { ...headers, 'content-type': 'application/atom+xml; charset=utf-8' } });
}

function unavailable(): Response {
  return new Response('The weekly digest could not be built right now. Try again in a few minutes.', {
    status: 502, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
  });
}
