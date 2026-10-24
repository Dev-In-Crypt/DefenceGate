import { redirect } from 'next/navigation';
import type { NextRequest } from 'next/server';
import { clearCookie, getUserState, SESSION_COOKIE } from '@/lib/account';
import { safeReturnPath } from '@/lib/safe-url';

export const dynamic = 'force-dynamic';

/**
 * Where a server component sends a visitor whose session the API refused (401): server components cannot
 * change cookies, a route handler can. The cookie is cleared only if the API really rejects it now, so a link
 * to this URL cannot sign anyone out. WP-116: the page asked for (`next`, an /app page only) is passed on.
 */
export async function GET(request: NextRequest) {
  const next = safeReturnPath(request.nextUrl.searchParams.get('next'));
  const state = await getUserState();
  if (state.kind === 'ok') redirect(next ?? '/app');
  if (state.kind === 'unauthorized') await clearCookie(SESSION_COOKIE);
  redirect(next ? `/signin?next=${encodeURIComponent(next)}` : '/signin');
}
