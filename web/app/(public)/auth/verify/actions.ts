'use server';

import { authVerify, isTokenShaped } from '@/lib/account';
import type { PlanChoice } from '@/lib/plans';

export interface ConfirmState {
  /** `invalid` covers every refusal (wrong, used, expired): one message, no detail. */
  status: 'idle' | 'done' | 'invalid' | 'unavailable';
  /** WP-123: the plan chosen on the pricing page before registering, said again once the address is confirmed. */
  choice?: PlanChoice | null;
}

/**
 * The only place a confirmation token is spent. It is called by the button on /auth/verify, never by a page render,
 * so a mail scanner that opens the link cannot use it up. It opens no session: the password does.
 */
export async function confirmAddress(_prev: ConfirmState, form: FormData): Promise<ConfirmState> {
  const token = form.get('token');
  if (!isTokenShaped(token)) return { status: 'invalid' };
  const r = await authVerify(token);
  if (r.ok) return { status: 'done', choice: r.data };
  return { status: r.status === 400 ? 'invalid' : 'unavailable' };
}
