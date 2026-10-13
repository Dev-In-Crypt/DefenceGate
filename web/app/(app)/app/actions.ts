'use server';

/**
 * State changes of the signed-in area. Every export is a server action: Next.js checks Origin against Host
 * before it runs, and the API accepts no cookie at all (the session is forwarded as a header by lib/account).
 * Each action ends in a redirect to a dynamic page with `?n=<code>`, so the forms work without JavaScript.
 */
import { redirect } from 'next/navigation';
import {
  authLogout, BIND_COOKIE, CADENCES, clearCookie, deleteFollow, deleteMe, deleteSearch, deleteShortlist, revokeOtherSessions,
  revokeSession, ROLES, SCOPES, SESSION_COOKIE, SHORTLIST_STATUSES, updateMe, updateSearch, putShortlist, type AccountResult,
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

/** The API checks the typed address against the account's own; here it is only passed on. */
export async function deleteAccount(form: FormData): Promise<void> {
  const typed = field(form, 'confirm', 254).trim();
  if (!typed) redirect('/app/settings?n=confirm');
  const r = await deleteMe(typed);
  if (r.ok) {
    await clearCookie(SESSION_COOKIE);
    await clearCookie(BIND_COOKIE);
    redirect('/');
  }
  if (r.status === 401) redirect('/auth/expired');
  redirect(`/app/settings?n=${r.status >= 400 && r.status < 500 ? 'confirm' : 'error'}`);
}
