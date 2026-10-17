import { NextResponse, type NextRequest } from 'next/server';
import { clientIp } from '@/lib/hits';

/**
 * The one call of the readiness check that leaves the browser: the answers go to the API, which computes the
 * verdict with its rules engine and stores nothing. This route only passes the body on. It does not read it, log it,
 * cache it or keep it; a failed or refused request is answered with the API's own short error, never with the body.
 *
 * It exists because the page's content policy allows connections to this site only (`connect-src 'self'`), and so
 * that the API need not be reachable from the internet for this call. The visitor's address goes with the request
 * (as it does for every list), so the API's rate limit is per visitor and not one bucket for the whole site.
 */
export const dynamic = 'force-dynamic';

const MAX_BYTES = 4096;       // the same limit as the proxy in front of the site (Caddy `request_body`)

function reply(body: unknown, status: number, extra: Record<string, string> = {}) {
  return NextResponse.json(body, { status, headers: { 'cache-control': 'no-store', ...extra } });
}

export async function POST(request: NextRequest) {
  const api = process.env.DG_API_URL;
  if (!api) return reply({ detail: 'the check is not available on this build' }, 503);
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
    const res = await fetch(`${api}/v1/readiness/assess`, {
      method: 'POST', headers, body, cache: 'no-store', signal: AbortSignal.timeout(10_000),
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...(res.headers.get('retry-after') ? { 'retry-after': res.headers.get('retry-after') as string } : {}) },
    });
  } catch {
    return reply({ detail: 'the check could not be computed' }, 502);
  }
}
