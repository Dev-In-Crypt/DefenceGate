import type { NextRequest } from 'next/server';
import { forwardPost } from '@/lib/api-proxy';

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

export async function POST(request: NextRequest) {
  return forwardPost(request, '/v1/readiness/assess', 'the check is not available on this build', 'the check could not be computed');
}
