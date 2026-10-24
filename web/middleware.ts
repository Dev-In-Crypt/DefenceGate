import { NextResponse, type NextFetchEvent, type NextRequest } from 'next/server';
import { clientIp, FLUSH_MS, HitBuffer, IpLimiter, referrerHost, routeKey } from './lib/hits';

/**
 * Visit counter. One aggregate row per day, page, referrer host and device class, written by the
 * site's own server: no cookie, no script in the page, no address, no user agent and no
 * identifier ever leaves this function. The page is counted, not the visitor (`/tenders/12-x`
 * becomes `/tenders/[slug]`), and the call is fire-and-forget: it can never slow or break a page.
 *
 * Page views are summed in memory and sent to the API in one batch every FLUSH_MS (lib/hits.ts), not one
 * request per view, and one address is counted at most 120 times a minute. The batch is sent by whichever
 * request finds it due, so a quiet site flushes on its next visit; a restart loses at most the last window.
 *
 * Not counted: anything that is not a plain page view (prefetches and data fetches, assets), and
 * clients that announce themselves as automated.
 */
export const config = {
  matcher: ['/((?!_next/|api/|brand/|auth/|.*\\..*).*)'],
};

const LIST_PATHS = new Set(['/tenders', '/funding', '/buyers']);
const AUTOMATED = /bot|crawl|spider|slurp|curl|wget|python|headless|monitor|preview|fetch|scan|check/i;
const MOBILE = /mobi|android|iphone|ipad/i;

const buffer = new HitBuffer();
const limiter = new IpLimiter();
let lastFlush = Date.now();

function flush(api: string, event: NextFetchEvent): void {
  const hits = buffer.drain();
  if (hits.length === 0) return;
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  const secret = process.env.DG_INTERNAL_SECRET;
  if (secret) headers['x-dg-internal'] = secret;
  event.waitUntil(
    fetch(`${api}/v1/internal/hits`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ hits }),
      signal: AbortSignal.timeout(3000),
    }).catch(() => undefined),
  );
}

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
    const now = Date.now();
    if (limiter.allow(clientIp(request.headers.get('x-forwarded-for')), now)) {
      const own = (request.headers.get('x-forwarded-host') ?? request.headers.get('host') ?? '').split(':')[0];
      buffer.add(routeKey(request.nextUrl.pathname), referrerHost(request.headers.get('referer'), own), MOBILE.test(agent));
    }
    if (now - lastFlush >= FLUSH_MS) {
      lastFlush = now;
      flush(api, event);
    }
  }
  // A list request past page 1 carries its query to the list layouts (lib/list-bounds.ts), which answer a page past
  // the end with a 307 before anything streams. The header is only ever read to build that redirect.
  const { pathname, search } = request.nextUrl;
  // WP-116: the signed-in area's layout sends a visitor without a session to /signin with the page asked for (`next`); a layout
  // is not told its path, so it is forwarded here (set, never appended: a header the client sent is replaced). The layout checks it.
  if (pathname === '/app' || pathname.startsWith('/app/')) {
    const forwarded = new Headers(request.headers);
    forwarded.set('x-dg-path', `${pathname}${search}`);
    return NextResponse.next({ request: { headers: forwarded } });
  }
  if (request.method === 'GET' && LIST_PATHS.has(pathname) && /[?&]page=(?:[2-9]|\d{2,})(?:&|$)/.test(search)) {
    const forwarded = new Headers(request.headers);
    forwarded.set('x-dg-search', search.slice(1));
    return NextResponse.next({ request: { headers: forwarded } });
  }
  return NextResponse.next();
}
