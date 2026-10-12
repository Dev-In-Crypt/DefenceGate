'use server';

import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { authVerify, BIND_COOKIE, isTokenShaped, SESSION_COOKIE, SESSION_MAX_AGE_SECONDS } from '@/lib/account';

export interface ConfirmState {
  /** `invalid` covers every refusal (wrong, used, expired, other browser): one message, no detail. */
  status: 'idle' | 'invalid' | 'unavailable';
}

/**
 * The only place a sign-in token is spent. It is called by the button on /auth/verify, never by a page render,
 * so a mail scanner that opens the link cannot use it up.
 */
export async function confirmSignIn(_prev: ConfirmState, form: FormData): Promise<ConfirmState> {
  const token = form.get('token');
  const jar = await cookies();
  const binder = jar.get(BIND_COOKIE)?.value;
  if (!isTokenShaped(token) || !isTokenShaped(binder)) return { status: 'invalid' };

  const r = await authVerify(token, binder);
  if (!r.ok) return { status: r.status === 400 ? 'invalid' : 'unavailable' };

  // Life of the cookie follows the session's own expiry, never longer than the contract's 30 days.
  const left = Math.floor((Date.parse(r.data.expiresAt) - Date.now()) / 1000);
  const maxAge = Number.isFinite(left) && left > 0 ? Math.min(left, SESSION_MAX_AGE_SECONDS) : SESSION_MAX_AGE_SECONDS;
  jar.set(SESSION_COOKIE, r.data.session, { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge });
  jar.delete({ name: BIND_COOKIE, path: '/auth' });

  redirect(r.data.isNew ? '/app/welcome' : '/app');
}
