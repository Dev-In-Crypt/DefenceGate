import { NextResponse, type NextFetchEvent, type NextRequest } from 'next/server';

/**
 * Visit counter. One aggregate row per day, page, referrer host and device class, written by the
 * site's own server: no cookie, no script in the page, no address, no user agent and no
 * identifier ever leaves this function. The page is counted, not the visitor (`/tenders/12-x`
 * becomes `/tenders/[slug]`), and the call is fire-and-forget: it can never slow or break a page.
 *
 * Not counted: anything that is not a plain page view (prefetches and data fetches, assets), and
 * clients that announce themselves as automated.
 */
export const config = {
  matcher: ['/((?!_next/|api/|brand/|auth/|.*\\..*).*)'],
};

const AUTOMATED = /bot|crawl|spider|slurp|curl|wget|python|headless|monitor|preview|fetch|scan|check/i;
const MOBILE = /mobi|android|iphone|ipad/i;

export function middleware(request: NextRequest, event: NextFetchEvent) {
  const api = process.env.DG_API_URL;
  const agent = request.headers.get('user-agent') ?? '';
  const isPageView =
    request.method === 'GET' &&
    !request.headers.get('rsc') &&
    !request.headers.get('next-router-prefetch') &&
    !request.headers.get('next-router-state-tree') &&
    request.headers.get('sec-purpose') === null &&
    request.headers.get('purpose') === null;

  if (api && isPageView && agent !== '' && !AUTOMATED.test(agent)) {
    event.waitUntil(
      fetch(`${api}/v1/internal/hit`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          route: request.nextUrl.pathname,
          referrer: request.headers.get('referer') ?? '',
          mobile: MOBILE.test(agent),
        }),
        signal: AbortSignal.timeout(1500),
      }).catch(() => undefined),
    );
  }
  return NextResponse.next();
}
