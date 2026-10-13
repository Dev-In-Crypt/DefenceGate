'use server';

import { randomBytes } from 'node:crypto';
import { authRequest, BIND_COOKIE, BIND_MAX_AGE_SECONDS, setCookie } from '@/lib/account';

export interface SignInState {
  /**
   * `sent` is the one answer for every address that passed the format check: the API answers 202 whether or
   * not the address exists, and so does this page.
   */
  status: 'idle' | 'sent' | 'invalid' | 'rate_limited' | 'unavailable';
  /** The address as typed, handed back only so a failed attempt does not empty the field. Never on `sent`. */
  email?: string;
}

const EMAIL_MAX = 254;

/**
 * Sets the `__Host-dg_bind` cookie (ties the link to this browser), then asks the API to mail the link.
 * Server actions are same-origin only: Next.js compares Origin with Host before this runs.
 */
export async function requestSignIn(_prev: SignInState, form: FormData): Promise<SignInState> {
  const raw = form.get('email');
  const email = typeof raw === 'string' ? raw.trim() : '';
  if (!email || email.length > EMAIL_MAX || !email.includes('@')) return { status: 'invalid', email: email.slice(0, EMAIL_MAX) };

  const binder = randomBytes(32).toString('base64url');
  await setCookie(BIND_COOKIE, binder, BIND_MAX_AGE_SECONDS);

  const r = await authRequest(email, binder);
  if (r.ok) return { status: 'sent' };
  if (r.status === 422) return { status: 'invalid', email };
  if (r.status === 429) return { status: 'rate_limited', email };
  return { status: 'unavailable', email };
}
