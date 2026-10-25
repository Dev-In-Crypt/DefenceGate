'use server';

/**
 * Registration, sign-in (password, then the code when two-step sign-in is on) and password reset. Every export
 * is a server action: Next.js compares Origin with Host before it runs, which is the CSRF control of these forms
 * (docs/SECURITY_REQUIREMENTS.md A6). Passwords are passed to the API and never handed back to the page.
 */
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import {
  authLogin, authRegister, authSecondStep, clearCookie, isTokenShaped, resetConfirm, resetRequest, SECOND_STEP_COOKIE,
  SECOND_STEP_MAX_AGE_SECONDS, SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, setCookie, type AccountResult, type SignInResult,
} from '@/lib/account';
import { readPlanChoice } from '@/lib/plans';
import { safeReturnPath } from '@/lib/safe-url';

export interface AuthState {
  /**
   * `sent` is the one answer for every address that passed the checks: the API answers 202 whether or not the
   * address has an account, and so does this page. `password` carries the API's reason in `message`.
   */
  status: 'idle' | 'sent' | 'done' | 'invalid' | 'password' | 'wrong' | 'not_verified' | 'expired' | 'rate_limited'
    | 'unavailable' | 'terms';
  /** The address as typed, handed back only so a failed attempt does not empty the field. Never on `sent`. */
  email?: string;
  message?: string;
}

const EMAIL_MAX = 254;
const PASSWORD_MAX = 1024;

function email(form: FormData): string {
  const raw = form.get('email');
  return typeof raw === 'string' ? raw.trim().slice(0, EMAIL_MAX) : '';
}
function secret(form: FormData, key: string): string {
  const raw = form.get(key);
  return typeof raw === 'string' ? raw.slice(0, PASSWORD_MAX) : '';
}
const looksLikeAddress = (v: string) => v.length > 2 && v.includes('@');

/** The answers every form shares. */
function failed(r: Extract<AccountResult<unknown>, { ok: false }>, address?: string): AuthState {
  if (r.status === 422 && r.error.startsWith('password_')) return { status: 'password', email: address, message: r.message };
  if (r.status === 422 && r.error === 'terms_not_accepted') return { status: 'terms', email: address };
  if (r.status === 422) return { status: 'invalid', email: address };
  if (r.status === 429) return { status: 'rate_limited', email: address };
  return { status: 'unavailable', email: address };
}

/** The /app page to return to (WP-116), from the form; anything but a plain /app path is dropped (lib/safe-url.ts). */
const nextOf = (form: FormData) => safeReturnPath(form.get('next'));

/**
 * A session: the cookie (its life follows the session's own expiry, never over 30 days), then the account: the welcome page
 * for a new one, else the page asked for. With two-step sign-in on, the code page first (it carries `next` on).
 */
async function finish(d: SignInResult, next: string | null): Promise<never> {
  if (d.kind === 'second_step') {
    await setCookie(SECOND_STEP_COOKIE, d.ticket, SECOND_STEP_MAX_AGE_SECONDS);
    redirect(next ? `/signin/code?next=${encodeURIComponent(next)}` : '/signin/code');
  }
  const left = Math.floor((Date.parse(d.expiresAt) - Date.now()) / 1000);
  const maxAge = Number.isFinite(left) && left > 0 ? Math.min(left, SESSION_MAX_AGE_SECONDS) : SESSION_MAX_AGE_SECONDS;
  await setCookie(SESSION_COOKIE, d.session, maxAge);
  redirect(d.isNew ? '/app/welcome' : next ?? '/app');
}

export async function register(_prev: AuthState, form: FormData): Promise<AuthState> {
  const address = email(form);
  const password = secret(form, 'password');
  if (!looksLikeAddress(address)) return { status: 'invalid', email: address };
  if (form.get('acceptTerms') !== 'on') return { status: 'terms', email: address };
  const r = await authRegister(address, password, {
    termsVersion: String(form.get('termsVersion') ?? '').slice(0, 20),
    privacyVersion: String(form.get('privacyVersion') ?? '').slice(0, 20),
  }, readPlanChoice(form.get('plan'), form.get('billing')));
  return r.ok ? { status: 'sent' } : failed(r, address);
}

export async function signIn(_prev: AuthState, form: FormData): Promise<AuthState> {
  const address = email(form);
  const password = secret(form, 'password');
  if (!looksLikeAddress(address) || !password) return { status: 'invalid', email: address };
  const r = await authLogin(address, password);
  if (r.ok) return finish(r.data, nextOf(form));
  if (r.status === 401) return { status: 'wrong', email: address };
  if (r.status === 403 && r.error === 'not_verified') return { status: 'not_verified', email: address };
  return failed(r, address);
}

export async function signInSecondStep(_prev: AuthState, form: FormData): Promise<AuthState> {
  const ticket = (await cookies()).get(SECOND_STEP_COOKIE)?.value;
  const code = secret(form, 'code').slice(0, 32);
  if (!isTokenShaped(ticket)) return { status: 'expired' };
  const r = await authSecondStep(ticket, code);
  if (r.ok) {
    await clearCookie(SECOND_STEP_COOKIE);
    return finish(r.data, nextOf(form));
  }
  if (r.status === 400) {
    await clearCookie(SECOND_STEP_COOKIE);
    return { status: 'expired' };
  }
  if (r.status === 401) return { status: 'wrong' };
  return failed(r);
}

export async function requestReset(_prev: AuthState, form: FormData): Promise<AuthState> {
  const address = email(form);
  if (!looksLikeAddress(address)) return { status: 'invalid', email: address };
  const r = await resetRequest(address);
  return r.ok ? { status: 'sent' } : failed(r, address);
}

export async function setNewPassword(_prev: AuthState, form: FormData): Promise<AuthState> {
  const token = form.get('token');
  if (!isTokenShaped(token)) return { status: 'expired' };
  const r = await resetConfirm(token, secret(form, 'password'));
  if (r.ok) return { status: 'done' };
  if (r.status === 400) return { status: 'expired' };
  return failed(r);
}
