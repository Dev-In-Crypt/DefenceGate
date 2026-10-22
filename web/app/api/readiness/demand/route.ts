import { NextResponse, type NextRequest } from 'next/server';
import { forwardPost } from '@/lib/api-proxy';
import type { Demand } from '@/lib/demand';
import mock from '@/lib/mock/demand.json';

/**
 * The demand map of the supplier report (WP-66): the CPV codes of the supplier page and the countries go to the API, which counts the
 * defence buyers and winners and stores nothing. Passed on as the readiness check is (`../assess/route.ts`): not read, logged or kept.
 *
 * A demo build (DG_USE_MOCK=1, no API: CI) answers every request with lib/mock/demand.json, the API's answer of 22 October 2026 for
 * the sample supplier of `e2e/fixtures/profile-es-sup-*.json` (WP-66 self-check; one Polish partnership named after its partners left out), whatever codes were sent.
 */
export const dynamic = 'force-dynamic';

const DEMO: Demand = mock;

export async function POST(request: NextRequest) {
  if (!process.env.DG_API_URL && process.env.DG_USE_MOCK === '1') return NextResponse.json(DEMO, { headers: { 'cache-control': 'no-store' } });
  return forwardPost(request, '/v1/readiness/demand', 'the demand map is not available on this build', 'the demand map could not be computed');
}
