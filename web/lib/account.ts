import 'server-only';
/**
 * The only module that talks to the account API (docs/design/ACCOUNT_CONTRACT.md).
 * The site is a backend for frontend: the browser never calls /v1/account/*. Everything here runs on the
 * server, with the session read from the `dg_session` cookie and forwarded as X-DG-Session.
 *
 * Nothing in this file logs. Tokens, binders, session ids and e-mail addresses never reach a log line.
 * No call throws: wrappers return an AccountResult so a failed call renders as an error state.
 */
import { cache } from 'react';
import { cookies, headers } from 'next/headers';
import { redirect } from 'next/navigation';
import type {
  AccountSession, Cadence, Dashboard, DashboardChange, DashboardClosing, DashboardFollowing, DashboardMatch, DashboardPulse,
  Follow, FollowKind, Me, Profile, ProfileScope, Role, SavedSearch, SearchFilters, SearchKind, ShortlistItem, ShortlistKind,
  ShortlistStatus, StateItem, StateKey, Track,
} from './types';

const API_BASE = process.env.DG_API_URL;

export const SESSION_COOKIE = 'dg_session';
export const BIND_COOKIE = 'dg_bind';
/** Upper bound of a session cookie's life: the contract's 30 days. */
export const SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;
export const BIND_MAX_AGE_SECONDS = 15 * 60;

/** URL-safe base64 of 256 bits is 43 characters; anything outside this shape is never placed in a header. */
const TOKEN_RE = /^[A-Za-z0-9_-]{16,256}$/;
export function isTokenShaped(v: unknown): v is string {
  return typeof v === 'string' && TOKEN_RE.test(v);
}

export const ROLES: readonly Role[] = ['supplier', 'prime', 'consultant', 'grant_writer', 'other'];
export const TRACKS: readonly Track[] = ['tenders', 'funding'];
export const SCOPES: readonly ProfileScope[] = ['core', 'all'];
export const CADENCES: readonly Cadence[] = ['instant', 'daily', 'weekly', 'off'];
export const SHORTLIST_STATUSES: readonly ShortlistStatus[] = ['watching', 'evaluating', 'bidding', 'submitted', 'dropped'];

/* ---- transport ---- */

export type AccountResult<T> =
  | { ok: true; data: T }
  /** status 0: the API could not be reached or is not configured. `error` is the contract's code. */
  | { ok: false; status: number; error: string; message?: string; retryAfter?: number };

export interface AccountInit {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  json?: unknown;
  /** false for calls that carry no session (status, sign-in request and verify). Default true. */
  session?: boolean;
}

/** First address of X-Forwarded-For, as Caddy sets it. Anything that is not an address is dropped. */
function clientIp(forwardedFor: string | null): string | null {
  const first = forwardedFor?.split(',')[0]?.trim();
  return first && /^[0-9A-Fa-f:.]{2,45}$/.test(first) ? first : null;
}

/** The session cookie's value when it is shaped like one. Never logged, never rendered. */
export async function readSession(): Promise<string | null> {
  const v = (await cookies()).get(SESSION_COOKIE)?.value;
  return isTokenShaped(v) ? v : null;
}

/**
 * Raw call to `${DG_API_URL}/v1/account${path}`. Throws when the API is not configured or unreachable;
 * a call that needs a session and has none answers 401 without a request. Callers that want a value use the
 * typed wrappers below, which never throw.
 */
export async function accountFetch(path: string, init: AccountInit = {}): Promise<Response> {
  if (!API_BASE) throw new Error('account API is not configured');
  const h: Record<string, string> = { accept: 'application/json' };
  if (init.session !== false) {
    const session = await readSession();
    if (!session) return new Response(null, { status: 401 });
    h['x-dg-session'] = session;
  }
  const ip = clientIp((await headers()).get('x-forwarded-for'));
  if (ip) h['x-dg-client-ip'] = ip;
  let body: string | undefined;
  if (init.json !== undefined) {
    h['content-type'] = 'application/json';
    body = JSON.stringify(init.json);
  }
  return fetch(`${API_BASE}/v1/account${path}`, {
    method: init.method ?? (body === undefined ? 'GET' : 'POST'),
    headers: h,
    body,
    cache: 'no-store',
    signal: AbortSignal.timeout(10_000),
  });
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

async function call<T>(path: string, init: AccountInit = {}, parse?: (raw: unknown) => T): Promise<AccountResult<T>> {
  let res: Response;
  try {
    res = await accountFetch(path, init);
  } catch {
    return { ok: false, status: 0, error: 'unavailable' };
  }
  let body: unknown = null;
  if (res.status !== 204) {
    try { body = await res.json(); } catch { /* an empty or non-JSON body */ }
  }
  if (!res.ok) {
    const b = isRecord(body) ? body : {};
    const retry = Number(res.headers.get('retry-after'));
    return {
      ok: false,
      status: res.status,
      error: typeof b.error === 'string' ? b.error : 'error',
      message: typeof b.message === 'string' ? b.message.slice(0, 200) : undefined,
      retryAfter: Number.isFinite(retry) && retry > 0 ? retry : undefined,
    };
  }
  try {
    return { ok: true, data: parse ? parse(body) : (body as T) };
  } catch {
    return { ok: false, status: 502, error: 'bad_response' };
  }
}

/* ---- shape guards: the API is trusted, a malformed answer is still not allowed to crash a page ---- */

const arr = <T>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const items = <T>(raw: unknown): T[] => arr<T>(isRecord(raw) ? raw.items : null);
const oneOf = <T extends string>(v: unknown, allowed: readonly T[]): T | null => (typeof v === 'string' && (allowed as readonly string[]).includes(v) ? (v as T) : null);

export function toProfile(raw: unknown): Profile {
  const p = isRecord(raw) ? raw : {};
  return {
    role: oneOf(p.role, ROLES),
    tracks: arr<unknown>(p.tracks).map((t) => oneOf(t, TRACKS)).filter((t): t is Track => t !== null),
    countries: arr<unknown>(p.countries).filter((c): c is string => typeof c === 'string' && /^[A-Z]{2}$/.test(c)),
    scope: oneOf(p.scope, SCOPES) ?? 'core',
    cadence: oneOf(p.cadence, CADENCES) ?? 'daily',
  };
}

function toMe(raw: unknown): Me {
  if (!isRecord(raw) || typeof raw.id !== 'string' || typeof raw.email !== 'string') throw new Error('bad me');
  return {
    id: raw.id,
    email: raw.email,
    createdAt: typeof raw.createdAt === 'string' ? raw.createdAt : '',
    profile: toProfile(raw.profile),
    onboarded: raw.onboarded === true,
    lastVisitAt: typeof raw.lastVisitAt === 'string' ? raw.lastVisitAt : null,
  };
}

function toDashboard(raw: unknown): Dashboard {
  const d = isRecord(raw) ? raw : {};
  const sl = isRecord(d.shortlist) ? d.shortlist : {};
  const counts: Dashboard['shortlist']['counts'] = {};
  if (isRecord(sl.counts)) {
    for (const s of SHORTLIST_STATUSES) if (typeof sl.counts[s] === 'number') counts[s] = sl.counts[s] as number;
  }
  const pulse = isRecord(d.pulse) ? (d.pulse as unknown as DashboardPulse) : null;
  return {
    lastVisitAt: typeof d.lastVisitAt === 'string' ? d.lastVisitAt : null,
    matches: arr<DashboardMatch>(d.matches).filter((m) => isRecord(m) && isRecord(m.search)).map((m): DashboardMatch => ({ ...m, items: arr(m.items) })),
    closingSoon: arr<DashboardClosing>(d.closingSoon).filter((c) => isRecord(c) && isRecord(c.item)),
    changes: arr<DashboardChange>(d.changes).filter((c) => isRecord(c) && isRecord(c.item)).map((c): DashboardChange => ({ ...c, changes: arr(c.changes) })),
    following: arr<DashboardFollowing>(d.following).filter((f) => isRecord(f)),
    shortlist: { counts, items: arr<ShortlistItem>(sl.items) },
    pulse,
  };
}

/**
 * For server components. A 401 sends the visitor through /auth/expired (which clears the dead cookie and goes to
 * /signin); any other failure returns null and the page renders an error state instead of crashing.
 */
export function dataOrNull<T>(r: AccountResult<T>): T | null {
  if (r.ok) return r.data;
  if (r.status === 401) redirect('/auth/expired');
  return null;
}

/* ---- status ---- */

/**
 * GET /v1/account/status, cached 60 seconds. Reads no cookie, so a static page can call it. Any failure is
 * "not open": the site then shows "Sign-in is not open yet" and sends nothing else.
 */
export async function getAccountStatus(): Promise<{ open: boolean }> {
  if (!API_BASE) return { open: false };
  try {
    const res = await fetch(`${API_BASE}/v1/account/status`, {
      headers: { accept: 'application/json' },
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!res.ok) return { open: false };
    const body: unknown = await res.json();
    return { open: isRecord(body) && body.open === true };
  } catch {
    return { open: false };
  }
}

/* ---- sign-in ---- */

export const authRequest = (email: string, binder: string) =>
  call<void>('/auth/request', { method: 'POST', json: { email, binder }, session: false });

export interface VerifiedSession { session: string; expiresAt: string; isNew: boolean }
export const authVerify = (token: string, binder: string) =>
  call<VerifiedSession>('/auth/verify', { method: 'POST', json: { token, binder }, session: false }, (raw) => {
    if (!isRecord(raw) || !isTokenShaped(raw.session)) throw new Error('bad session');
    return { session: raw.session, expiresAt: typeof raw.expiresAt === 'string' ? raw.expiresAt : '', isNew: raw.isNew === true };
  });

export const authLogout = () => call<void>('/auth/logout', { method: 'POST' });

/* ---- account ---- */

export const getMe = () => call<Me>('/me', {}, toMe);
export const updateMe = (patch: Partial<Profile>) => call<Me>('/me', { method: 'PATCH', json: patch }, toMe);
export const deleteMe = (confirm: string) => call<void>('/me', { method: 'DELETE', json: { confirm } });

export type UserState =
  | { kind: 'ok'; user: Me }
  /** No session cookie. */
  | { kind: 'anonymous' }
  /** The API refused the session (401). */
  | { kind: 'unauthorized' }
  /** The API could not be reached or answered something else. The session may still be good. */
  | { kind: 'unavailable' };

/** One lookup per request, shared by the layout and the page. Never throws. */
export const getUserState = cache(async (): Promise<UserState> => {
  if (!(await readSession())) return { kind: 'anonymous' };
  const r = await getMe();
  if (r.ok) return { kind: 'ok', user: r.data };
  return r.status === 401 ? { kind: 'unauthorized' } : { kind: 'unavailable' };
});

/** The signed-in account, or null for anything else (no cookie, rejected session, API down). Never throws. */
export async function getCurrentUser(): Promise<Me | null> {
  const s = await getUserState();
  return s.kind === 'ok' ? s.user : null;
}

export const listSessions = () => call<AccountSession[]>('/sessions', {}, (raw) => (Array.isArray(raw) ? (raw as AccountSession[]) : items<AccountSession>(raw)));
export const revokeSession = (id: string) => call<void>(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const revokeOtherSessions = () => call<void>('/sessions', { method: 'DELETE' });

/* ---- saved searches ---- */

export const listSearches = () => call<SavedSearch[]>('/searches', {}, (raw) => items<SavedSearch>(raw));
export const createSearch = (s: { name: string; kind: SearchKind; filters: SearchFilters; cadence?: Cadence }) =>
  call<SavedSearch>('/searches', { method: 'POST', json: s });
export const updateSearch = (id: string, patch: { name?: string; cadence?: Cadence }) =>
  call<SavedSearch>(`/searches/${encodeURIComponent(id)}`, { method: 'PATCH', json: patch });
export const deleteSearch = (id: string) => call<void>(`/searches/${encodeURIComponent(id)}`, { method: 'DELETE' });

/* ---- shortlist and follows ---- */

export const listShortlist = () => call<ShortlistItem[]>('/shortlist', {}, (raw) => items<ShortlistItem>(raw));
export const putShortlist = (kind: ShortlistKind, ref: string, status: ShortlistStatus, note: string) =>
  call<ShortlistItem | null>(`/shortlist/${kind}/${encodeURIComponent(ref)}`, { method: 'PUT', json: { status, note } });
export const deleteShortlist = (kind: ShortlistKind, ref: string) =>
  call<void>(`/shortlist/${kind}/${encodeURIComponent(ref)}`, { method: 'DELETE' });

export const listFollows = () => call<Follow[]>('/follows', {}, (raw) => items<Follow>(raw));
export const putFollow = (kind: FollowKind, ref: string) =>
  call<Follow | null>(`/follows/${kind}/${encodeURIComponent(ref)}`, { method: 'PUT' });
export const deleteFollow = (kind: FollowKind, ref: string) =>
  call<void>(`/follows/${kind}/${encodeURIComponent(ref)}`, { method: 'DELETE' });

/** At most 50 keys. */
export const getState = (keys: StateKey[]) =>
  call<StateItem[]>('/state', { method: 'POST', json: { keys } }, (raw) => items<StateItem>(raw));

/* ---- dashboard ---- */

/** Also moves the account's lastVisitAt: the API does that on this call only. */
export const getDashboard = () => call<Dashboard>('/dashboard', {}, toDashboard);
