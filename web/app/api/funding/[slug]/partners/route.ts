import { NextResponse, type NextRequest } from 'next/server';
import { forwardGet } from '@/lib/api-proxy';

/** GET /api/funding/{slug}/partners?country=XX: organisations of earlier projects in the call's area. Carries no profile. */
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!/^[0-9]{1,9}(-[a-z0-9-]{0,80})?$/.test(slug)) return NextResponse.json({ detail: 'no such call' }, { status: 404 });
  const query = new URLSearchParams();
  const country = request.nextUrl.searchParams.get('country');
  if (country) {
    if (!/^[A-Za-z]{2}$/.test(country)) return NextResponse.json({ detail: 'country: two letters' }, { status: 422 });
    query.set('country', country.toUpperCase());
  }
  const limit = request.nextUrl.searchParams.get('limit');
  if (limit) {
    if (!/^[0-9]{1,2}$/.test(limit)) return NextResponse.json({ detail: 'limit: a number up to 50' }, { status: 422 });
    query.set('limit', limit);
  }
  return forwardGet(request, `/v1/funding/${slug}/partners${query.size ? `?${query}` : ''}`);
}
