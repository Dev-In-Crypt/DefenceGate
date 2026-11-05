'use server';

import { authVerify, isTokenShaped } from '@/lib/account';
import type { PlanChoice } from '@/lib/plans';

export interface ConfirmState {
  /** `invalid` covers every refusal of the link (wrong, used, expired): one message, no detail. `wrong_password`: the
   *  password is not the one the account was created with (the link stays usable). */
  status: 'idle' | 'done' | 'invalid' | 'wrong_password' | 'rate_limited' | 'unavailable';
  /** WP-123: the plan chosen on the pricing page before registering, said again once the address is confirmed. */
  choice?: PlanChoice | null;
}

const PASSWORD_MAX = 1024;

/**
 * The only place a confirmation token is spent. It is called by the button on /auth/verify, never by a page render,
 * so a mail scanner that opens the link cannot use it up. It asks for the password the account was created with, so a
 * registration of this address by someone else cannot be confirmed by mistake. It opens no session: signing in does.
 */
export async function confirmAddress(_prev: ConfirmState, form: FormData): Promise<ConfirmState> {
  const token = form.get('token');
  const password = form.get('password');
  if (!isTokenShaped(token)) return { status: 'invalid' };
  if (typeof password !== 'string' || !password || password.length > PASSWORD_MAX) return { status: 'wrong_password' };
  const r = await authVerify(token, password);
  if (r.ok) return { status: 'done', choice: r.data };
  if (r.status === 403) return { status: 'wrong_password' };
  if (r.status === 429) return { status: 'rate_limited' };
  return { status: r.status === 400 ? 'invalid' : 'unavailable' };
}
