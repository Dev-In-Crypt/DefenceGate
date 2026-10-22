import { NextResponse, type NextRequest } from 'next/server';
import { forwardPost } from '@/lib/api-proxy';
import type { Demand, WinnersPage } from '@/lib/demand';
import mock from '@/lib/mock/demand.json';

/**
 * WP-81: every winner of the demand answer for the profile's codes, a page at a time (`POST /v1/readiness/winners`). Passed on as the
 * demand map is (`../demand/route.ts`): not read, logged or kept.
 *
 * A demo build (DG_USE_MOCK=1, no API: CI) answers with the named winners of lib/mock/demand.json, in pages of 20 so that the paging shows.
 */
export const dynamic = 'force-dynamic';

const DEMO: Demand = mock;
const DEMO_PAGE = 20;

export async function POST(request: NextRequest) {
  if (!process.env.DG_API_URL && process.env.DG_USE_MOCK === '1') {
    const body = (await request.json().catch(() => ({}))) as { page?: number; countries?: string[] };
    const page = Math.max(1, Math.floor(Number(body.page) || 1));
    const asked = Array.isArray(body.countries) && body.countries.length ? body.countries : DEMO.countries;
    const all = DEMO.approach.winners.filter((w) => w.countries.some((c) => asked.includes(c)));
    const out: WinnersPage = {
      since: DEMO.since, until: DEMO.until, countries: asked, total: all.length, page, pageSize: DEMO_PAGE,
      winners: all.slice((page - 1) * DEMO_PAGE, page * DEMO_PAGE), winnersFrom: DEMO.winnersFrom, sources: DEMO.sources,
    };
    return NextResponse.json(out, { headers: { 'cache-control': 'no-store' } });
  }
  return forwardPost(request, '/v1/readiness/winners', 'the list of winners is not available on this build', 'the list of winners could not be computed');
}
