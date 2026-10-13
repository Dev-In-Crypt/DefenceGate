import { redirect } from 'next/navigation';
import { clearCookie, getUserState, SESSION_COOKIE } from '@/lib/account';

export const dynamic = 'force-dynamic';

/**
 * Where a server component sends a visitor whose session the API refused (401): server components cannot
 * change cookies, a route handler can. The cookie is cleared only if the API really rejects it now, so a link
 * to this URL cannot sign anyone out.
 */
export async function GET() {
  const state = await getUserState();
  if (state.kind === 'ok') redirect('/app');
  if (state.kind === 'unauthorized') await clearCookie(SESSION_COOKIE);
  redirect('/signin');
}
