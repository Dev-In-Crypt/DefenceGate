'use server';

/**
 * State changes of the signed-in area. Every export is a server action: Next.js checks Origin against Host
 * before it runs, and the API accepts no cookie at all (the session is forwarded as a header by lib/account).
 * Each action ends in a redirect to a dynamic page with `?n=<code>`, so the forms work without JavaScript.
 */
import { redirect } from 'next/navigation';
import {
  acceptTerms, authLogout, CADENCES, changePassword, clearCookie, deleteFollow, deleteMe, deleteSearch, deleteShortlist,
  revokeOtherSessions, revokeSession, ROLES, SCOPES, SESSION_COOKIE, SHORTLIST_STATUSES, totpDisable, totpEnable, totpSetup,
  updateMe, updateSearch, putShortlist, type AccountResult,
} from '@/lib/account';
import { followRef, isUuid, numericRef } from '@/lib/refs';
import type { Cadence, FollowKind, Profile, ProfileScope, Role, ShortlistKind, ShortlistStatus, Track } from '@/lib/types';

const COUNTRY_RE = /^[A-Z]{2}$/;
const MAX_COUNTRIES = 20;
const NOTE_MAX = 500;

function field(form: FormData, key: string, max = 256): string {
  const v = form.get(key);
  return typeof v === 'string' ? v.slice(0, max) : '';
}
function pick<T extends string>(v: string, allowed: readonly T[]): T | null {
  return (allowed as readonly string[]).includes(v) ? (v as T) : null;
}

/** Back to a page with the outcome. A 401 goes through /auth/expired, which clears the dead cookie. */
function back(path: string, r: AccountResult<unknown>, ok: string = 'saved'): never {
  if (!r.ok && r.status === 401) redirect('/auth/expired');
  redirect(`${path}?n=${r.ok ? ok : r.status === 422 ? 'invalid' : 'error'}`);
}

export async function acceptCurrentTerms(form: FormData): Promise<void> {
  const r = await acceptTerms({ termsVersion: field(form, 'termsVersion', 20), privacyVersion: field(form, 'privacyVersion', 20) });
  back('/app', r, 'saved');
}

export async function signOut(): Promise<void> {
  // Best effort on the API side (its session expires on its own); the cookie goes either way, also if the
  // call throws, which is why it is a `finally`.
  try {
    await authLogout();
  } finally {
    await clearCookie(SESSION_COOKIE);
  }
  redirect('/');
}

/* ---- profile ---- */

function parseProfile(form: FormData): Profile | 'invalid' | 'countries' {
  const role = pick(field(form, 'role', 32), ROLES);
  const t = field(form, 'tracks', 16);
  const tracks: Track[] | null = t === 'both' ? ['tenders', 'funding'] : t === 'tenders' || t === 'funding' ? [t] : null;
  const scope = pick(field(form, 'scope', 8), SCOPES);
  const cadence = pick(field(form, 'cadence', 8), CADENCES);
  if (!role || !tracks || !scope || !cadence) return 'invalid';
  const countries = [...new Set(form.getAll('countries').filter((c): c is string => typeof c === 'string' && COUNTRY_RE.test(c)))];
  if (countries.length > MAX_COUNTRIES) return 'countries';
  return { role: role as Role, tracks, countries, scope: scope as ProfileScope, cadence: cadence as Cadence };
}

export async function saveWelcome(form: FormData): Promise<void> {
  const p = parseProfile(form);
  if (typeof p === 'string') redirect(`/app/welcome?n=${p}`);
  const r = await updateMe(p);
  if (r.ok) redirect('/app');
  back('/app/welcome', r);
}

export async function saveSettings(form: FormData): Promise<void> {
  const p = parseProfile(form);
  if (typeof p === 'string') redirect(`/app/settings?n=${p}`);
  back('/app/settings', await updateMe(p));
}

/* ---- saved searches ---- */

export async function setSearchCadence(form: FormData): Promise<void> {
  const id = field(form, 'id', 64);
  const cadence = pick(field(form, 'cadence', 8), CADENCES);
  if (!isUuid(id) || !cadence) redirect('/app/searches?n=invalid');
  back('/app/searches', await updateSearch(id, { cadence }));
}

export async function removeSearch(form: FormData): Promise<void> {
  const id = field(form, 'id', 64);
  if (!isUuid(id)) redirect('/app/searches?n=invalid');
  const r = await deleteSearch(id);
  back('/app/searches', r.ok || r.status === 404 ? { ok: true, data: undefined } : r, 'removed');
}

/* ---- shortlist and follows ---- */

export async function saveShortlistItem(form: FormData): Promise<void> {
  const kind = pick(field(form, 'kind', 8), ['tender', 'call'] as const);
  const ref = numericRef(field(form, 'ref', 64));
  const status = pick(field(form, 'status', 16), SHORTLIST_STATUSES);
  if (!kind || ref === null || !status) redirect('/app/shortlist?n=invalid');
  const note = field(form, 'note', NOTE_MAX * 2).trim().slice(0, NOTE_MAX);
  back('/app/shortlist', await putShortlist(kind as ShortlistKind, ref, status as ShortlistStatus, note));
}

export async function removeShortlistItem(form: FormData): Promise<void> {
  const kind = pick(field(form, 'kind', 8), ['tender', 'call'] as const);
  const ref = numericRef(field(form, 'ref', 64));
  if (!kind || ref === null) redirect('/app/shortlist?n=invalid');
  const r = await deleteShortlist(kind as ShortlistKind, ref);
  back('/app/shortlist', r.ok || r.status === 404 ? { ok: true, data: undefined } : r, 'removed');
}

export async function unfollow(form: FormData): Promise<void> {
  const kind = pick(field(form, 'kind', 12), ['buyer', 'programme'] as const);
  const ref = kind ? followRef(kind, field(form, 'ref', 64)) : null;
  if (!kind || ref === null) redirect('/app/following?n=invalid');
  const r = await deleteFollow(kind as FollowKind, ref);
  back('/app/following', r.ok || r.status === 404 ? { ok: true, data: undefined } : r, 'removed');
}

/* ---- sessions and the account itself ---- */

export async function endSession(form: FormData): Promise<void> {
  const id = field(form, 'id', 64);
  if (!isUuid(id)) redirect('/app/settings?n=invalid');
  back('/app/settings', await revokeSession(id), 'revoked');
}

export async function endOtherSessions(): Promise<void> {
  back('/app/settings', await revokeOtherSessions(), 'revoked');
}

/** Every other session first, then this one: the account is signed out everywhere. */
export async function signOutEverywhere(): Promise<void> {
  const r = await revokeOtherSessions();
  if (!r.ok && r.status !== 401) redirect('/app/settings?n=error');
  await signOut();
}

/* ---- password and two-step sign-in ---- */

const PASSWORD_MAX = 1024;

/** The code of a refused password or code, as `?n=` of the settings page. */
function securityCode(r: Extract<AccountResult<unknown>, { ok: false }>): string {
  if (r.status === 401) redirect('/auth/expired');
  if (r.status === 403) return 'wrong_password';
  if (r.status === 429) return 'rate_limited';
  if (r.status === 422 && r.error.startsWith('password_')) return 'weak';
  return 'error';
}

export async function changeMyPassword(form: FormData): Promise<void> {
  const r = await changePassword(field(form, 'currentPassword', PASSWORD_MAX), field(form, 'newPassword', PASSWORD_MAX));
  redirect(`/app/settings?n=${r.ok ? 'password' : securityCode(r)}#password`);
}

export interface TotpState {
  status: 'idle' | 'setup' | 'on' | 'wrong_password' | 'invalid_code' | 'rate_limited' | 'error';
  /** The key to type into an authenticator app, and the same as an otpauth:// link. Only in the answer to `startTotp`. */
  secret?: string;
  uri?: string;
  /** Shown once, in the answer to `confirmTotp`. */
  codes?: string[];
}

export async function startTotp(_prev: TotpState, form: FormData): Promise<TotpState> {
  const r = await totpSetup(field(form, 'password', PASSWORD_MAX));
  if (r.ok) return { status: 'setup', secret: r.data.secret, uri: r.data.uri };
  const code = securityCode(r);
  return { status: code === 'wrong_password' || code === 'rate_limited' ? code : 'error' };
}

export async function confirmTotp(_prev: TotpState, form: FormData): Promise<TotpState> {
  const r = await totpEnable(field(form, 'code', 32));
  if (r.ok) return { status: 'on', codes: r.data };
  const code = securityCode(r);
  if (r.status === 422) return { status: 'invalid_code' };
  return { status: code === 'rate_limited' ? code : 'error' };
}

export async function stopTotp(form: FormData): Promise<void> {
  const r = await totpDisable(field(form, 'password', PASSWORD_MAX));
  redirect(`/app/settings?n=${r.ok ? 'totp_off' : securityCode(r)}#two-step`);
}

/** The API checks the typed address against the account's own, and the password (WP-123); here they are only passed on. */
export async function deleteAccount(form: FormData): Promise<void> {
  const typed = field(form, 'confirm', 254).trim();
  if (!typed) redirect('/app/settings?n=confirm#delete');
  const r = await deleteMe(typed, field(form, 'password', PASSWORD_MAX));
  if (r.ok) {
    await clearCookie(SESSION_COOKIE);
    redirect('/');
  }
  if (r.status === 401) redirect('/auth/expired');
  const code = r.status === 403 && r.error === 'wrong_password' ? 'wrong_password' : r.status === 429 ? 'rate_limited'
    : r.status >= 400 && r.status < 500 ? 'confirm' : 'error';
  redirect(`/app/settings?n=${code}#delete`);
}
