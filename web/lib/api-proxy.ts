import { NextResponse, type NextRequest } from 'next/server';
import { clientIp } from './hits';

/**
 * The browser may only connect to this site (`connect-src 'self'`), so the two public reads that a visitor's browser
 * makes on its own (the facts behind the "fits my profile" badge, and partner suggestions) go through the site. The
 * route only passes a validated GET on: it carries no profile and keeps nothing. The visitor's address goes with the
 * request, as it does for the readiness check, so the API's rate limit is per visitor and not one bucket for the site.
 */
const MAX_BYTES = 4096;       // the same limit as the proxy in front of the site (Caddy `request_body`)

function reply(body: unknown, status: number) {
  return NextResponse.json(body, { status, headers: { 'cache-control': 'no-store' } });
}

/**
 * Passes a JSON body on to the API (the readiness check and the demand map). It does not read the body, log it, cache it or keep it;
 * a failed or refused request is answered with the API's own short error, never with the body. `unavailable` is what a build without
 * an API says.
 */
export async function forwardPost(request: NextRequest, path: string, unavailable: string, failed: string): Promise<NextResponse> {
  const api = process.env.DG_API_URL;
  if (!api) return reply({ detail: unavailable }, 503);
  if (!(request.headers.get('content-type') ?? '').toLowerCase().startsWith('application/json')) return reply({ detail: 'send JSON' }, 415);
  const declared = Number(request.headers.get('content-length') ?? '0');
  if (declared > MAX_BYTES) return reply({ detail: 'request body too large' }, 413);
  const body = await request.text();
  if (body.length > MAX_BYTES) return reply({ detail: 'request body too large' }, 413);

  const headers: Record<string, string> = { 'content-type': 'application/json', accept: 'application/json' };
  const ip = clientIp(request.headers.get('x-forwarded-for'));
  if (ip !== 'unknown') {
    headers['x-dg-client-ip'] = ip;
    if (process.env.DG_INTERNAL_SECRET) headers['x-dg-internal'] = process.env.DG_INTERNAL_SECRET;
  }
  try {
    const res = await fetch(`${api}${path}`, { method: 'POST', headers, body, cache: 'no-store', signal: AbortSignal.timeout(10_000) });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...(res.headers.get('retry-after') ? { 'retry-after': res.headers.get('retry-after') as string } : {}) },
    });
  } catch {
    return reply({ detail: failed }, 502);
  }
}

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
