import { NextResponse, type NextRequest } from 'next/server';
import { forwardGet } from '@/lib/api-proxy';

/** GET /api/fit/facts?ids=1,2,3: the document facts of up to 100 calls, for the badges of a list. Carries no profile. */
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const ids = request.nextUrl.searchParams.get('ids') ?? '';
  if (!/^[0-9]{1,9}(,[0-9]{1,9}){0,99}$/.test(ids)) return NextResponse.json({ detail: 'ids: up to 100 call ids, comma separated' }, { status: 422 });
  return forwardGet(request, `/v1/fit/facts?ids=${ids}`);
}
