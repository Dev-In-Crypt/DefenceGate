import { NextResponse, type NextRequest } from 'next/server';
import { clientIp } from './hits';

/**
 * The browser may only connect to this site (`connect-src 'self'`), so the two public reads that a visitor's browser
 * makes on its own (the facts behind the "fits my profile" badge, and partner suggestions) go through the site. The
 * route only passes a validated GET on: it carries no profile and keeps nothing. The visitor's address goes with the
 * request, as it does for the readiness check, so the API's rate limit is per visitor and not one bucket for the site.
 */
export async function forwardGet(request: NextRequest, path: string): Promise<NextResponse> {
  const api = process.env.DG_API_URL;
  if (!api) return NextResponse.json({ detail: 'not available on this build' }, { status: 503, headers: { 'cache-control': 'no-store' } });
  const headers: Record<string, string> = { accept: 'application/json' };
  const ip = clientIp(request.headers.get('x-forwarded-for'));
  if (ip !== 'unknown') {
    headers['x-dg-client-ip'] = ip;
    if (process.env.DG_INTERNAL_SECRET) headers['x-dg-internal'] = process.env.DG_INTERNAL_SECRET;
  }
  try {
    const res = await fetch(`${api}${path}`, { headers, cache: 'no-store', signal: AbortSignal.timeout(10_000) });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: {
        'content-type': 'application/json',
        // Public data about calls and projects: a browser may keep it for a few minutes.
        'cache-control': res.ok ? 'private, max-age=300' : 'no-store',
        ...(res.headers.get('retry-after') ? { 'retry-after': res.headers.get('retry-after') as string } : {}),
      },
    });
  } catch {
    return NextResponse.json({ detail: 'the read could not be completed' }, { status: 502, headers: { 'cache-control': 'no-store' } });
  }
}
