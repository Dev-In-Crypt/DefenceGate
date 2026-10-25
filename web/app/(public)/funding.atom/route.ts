import { getCalls } from '@/lib/api';
import { withCachedEtag } from '@/lib/etag';
import { searchParamsOf } from '@/lib/export';
import { describeCallFilters, ignoredFilters, parseCallFilters, toQuery, unknownParams } from '@/lib/filters';
import { FUNDING_SEARCH_PARAMS, buildFundingAtom } from '@/lib/funding-feed';
import { SITE } from '@/lib/seo';

const PLAIN = 'text/plain; charset=utf-8';
const ALL_CALLS = 500;          // the API's page ceiling: the feed holds the newest FUNDING_FEED_MAX of them

/**
 * WP-99: the Atom feed of a funding search, with exactly the filters of /funding (lib/funding-feed.ts). A parameter it does not read,
 * or a value it cannot use, is refused (as /funding.ics). It answers conditional requests and is kept for an hour, as the list is.
 */
export async function GET(request: Request): Promise<Response> {
  // WP-120: the built feed is kept for its own max-age, so a revalidation (304) costs no build (1.45 s on 25 October 2026)
  return withCachedEtag(request, MAX_AGE_S * 1000, () => build(request));
}

const MAX_AGE_S = 3600;

async function build(request: Request): Promise<Response> {
  const { page: _p, view: _v, ...sp } = searchParamsOf(new URL(request.url));
  const notices = [...unknownParams(sp, FUNDING_SEARCH_PARAMS), ...ignoredFilters(sp, 'funding')];
  if (notices.length > 0) {
    return new Response([...notices, `The feed reads the filters of /funding: ${FUNDING_SEARCH_PARAMS.join(', ')}.`].join('\n'),
      { status: 422, headers: { 'content-type': PLAIN, 'cache-control': 'no-store' } });
  }
  const f = parseCallFilters(sp);
  const data = await getCalls({ ...f, sort: undefined, page: 1, pageSize: ALL_CALLS }).catch(() => null);
  if (!data) {
    return new Response('The feed could not be built right now. Try again in a few minutes.', { status: 502, headers: { 'content-type': PLAIN, 'cache-control': 'no-store' } });
  }
  const body = buildFundingAtom(data.items, {
    origin: SITE.url.replace(/\/$/, ''), query: toQuery({ ...f, page: 1, sort: undefined }), describe: describeCallFilters(f).join(', '),
    total: data.total, generatedAt: new Date().toISOString(),
  });
  return new Response(body, { headers: { 'cache-control': `public, max-age=${MAX_AGE_S}`, 'content-type': 'application/atom+xml; charset=utf-8' } });
}
