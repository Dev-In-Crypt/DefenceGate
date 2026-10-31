import 'server-only';
/**
 * The only module that talks to the account API (docs/design/ACCOUNT_CONTRACT.md).
 * The site is a backend for frontend: the browser never calls /v1/account/*. Everything here runs on the
 * server, with the session read from the `__Host-dg_session` cookie and forwarded as X-DG-Session. Every call
 * also carries `X-DG-Internal` (DG_INTERNAL_SECRET, never sent to a browser) when it is configured: the API
 * then refuses anything that does not come from this server.
 *
 * Nothing in this file logs. Passwords, tokens, tickets, session ids and e-mail addresses never reach a log line.
 * No call throws: wrappers return an AccountResult so a failed call renders as an error state.
 */
import { cache } from 'react';
import { cookies, headers } from 'next/headers';
import { redirect } from 'next/navigation';
import type {
  AccountSession, ApiKey, ApiKeys, AssociationView, Cadence, Dashboard, DashboardChange, DashboardClosing, DashboardFollowing, DashboardMatch, DashboardPulse,
  Follow, FollowKind, Me, Profile, ProfileScope, Role, SavedSearch, SearchFilters, SearchKind, ShortlistItem, ShortlistKind,
  ShortlistStatus, StateItem, StateKey, Track, PaidFeature as Feature, SupplierCompetition, SupplierFilters, SupplierItem,
} from './types';
import { PAID_FEATURES } from './types';
import { PLAN_LABELS, readPlanChoice, type Billing, type PlanChoice, type PlanId } from './plans';
import { signalQuery, type SignalAnswer, type SignalFilters } from './signals';
import { endingQuery, type EndingAnswer, type EndingFilters } from './contract-period';
import type { PackAnswer } from './eligibility-pack';

const API_BASE = process.env.DG_API_URL;
const INTERNAL_SECRET = process.env.DG_INTERNAL_SECRET;

/**
 * `__Host-` cookies: the browser accepts them only with `Secure`, `Path=/` and no `Domain`, so a sibling
 * subdomain or a plain-http response cannot set or shadow them (review of 13 October 2026, M5).
 */
export const SESSION_COOKIE = '__Host-dg_session';
/** The ticket between the password and the second step (TOTP), for its 5 minutes only. */
export const SECOND_STEP_COOKIE = '__Host-dg_mfa';
const COOKIE_BASE = { httpOnly: true, secure: true, sameSite: 'lax', path: '/' } as const;

/** Set one of the two cookies with the attributes the `__Host-` prefix requires. */
export async function setCookie(name: string, value: string, maxAge: number): Promise<void> {
  (await cookies()).set(name, value, { ...COOKIE_BASE, maxAge });
}

/**
 * Remove a cookie. `cookies().delete()` writes a Set-Cookie without `Secure`, which a browser refuses for a
 * `__Host-` name, so the cookie would stay: it is overwritten with an expired, empty, Secure one instead.
 */
export async function clearCookie(name: string): Promise<void> {
  (await cookies()).set(name, '', { ...COOKIE_BASE, maxAge: 0, expires: new Date(0) });
}
/** Upper bound of a session cookie's life: the contract's 30 days. */
export const SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;
export const SECOND_STEP_MAX_AGE_SECONDS = 5 * 60;

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
  /** false for calls that carry no session (status, registration, sign-in, verify, reset). Default true. */
  session?: boolean;
  /** WP-156: how long to wait for the answer; 10 s by default, longer for an export of thousands of rows. */
  timeoutMs?: number;
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
  if (INTERNAL_SECRET) h['x-dg-internal'] = INTERNAL_SECRET;
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
    signal: AbortSignal.timeout(init.timeoutMs ?? 10_000),
  });
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

/** WP-157: exported for lib/workspace.ts (the workspace and client profile calls). */
export async function call<T>(path: string, init: AccountInit = {}, parse?: (raw: unknown) => T): Promise<AccountResult<T>> {
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
    reportName: typeof p.reportName === 'string' ? p.reportName.slice(0, 80) : null,
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
    termsCurrent: isRecord(raw.terms) && raw.terms.current === true,
    hasPassword: isRecord(raw.security) && raw.security.hasPassword === true,
    totp: isRecord(raw.security) && raw.security.totp === true,
    planChoice: isRecord(raw.plan) ? readPlanChoice(raw.plan.chosen, raw.plan.billing) : null,
    plan: isRecord(raw.plan) ? toPlan(raw.plan.current) : 'free',
    features: toFeatures(raw.features),
    apiKeys: arr<unknown>(raw.features).includes('api_keys'),
    association: arr<unknown>(raw.features).includes('association'),
    limits: toLimits(raw.limits),
    workspace: isRecord(raw.workspace) ? { role: raw.workspace.role === 'owner' ? 'owner' : 'member', active: raw.workspace.active === true } : null,
  };
}

function toLimits(raw: unknown): Me['limits'] {
  const l = isRecord(raw) ? raw : {};
  const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : null);
  return { savedSearches: n(l.savedSearches) ?? 10, reportsPerMonth: n(l.reportsPerMonth) };
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
export interface AccountStatus {
  open: boolean; termsVersion: string | null; privacyVersion: string | null;
  /** WP-124: the API has every Creem setting (and accounts are open). The site also needs NEXT_PUBLIC_BILLING_OPEN (lib/plans billingOpen). */
  billing: boolean;
  /** WP-155: the plans are on sale (every Creem product id set): a paid feature is then the plans'. Until then nobody is refused one. */
  plansOnSale: boolean;
}

export async function getAccountStatus(): Promise<AccountStatus> {
  const closed = { open: false, termsVersion: null, privacyVersion: null, billing: false, plansOnSale: false };
  if (!API_BASE) return closed;
  try {
    const res = await fetch(`${API_BASE}/v1/account/status`, {
      headers: INTERNAL_SECRET ? { accept: 'application/json', 'x-dg-internal': INTERNAL_SECRET } : { accept: 'application/json' },
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!res.ok) return closed;
    const body: unknown = await res.json();
    if (!isRecord(body)) return closed;
    const version = (v: unknown) => (typeof v === 'string' && /^[0-9.]{1,20}$/.test(v) ? v : null);
    return { open: body.open === true, termsVersion: version(body.termsVersion), privacyVersion: version(body.privacyVersion),
      billing: body.open === true && body.billing === true, plansOnSale: body.plansOnSale === true };
  } catch {
    return closed;
  }
}

/* ---- registration and sign-in ---- */

/** The tick on the form, with the versions of the two texts the form showed (the API refuses anything else). */
export interface TermsTick { termsVersion: string; privacyVersion: string }

/**
 * 202 for every address that passed the checks, whether or not it has an account (the mail differs). WP-123: with the plan
 * picked on the pricing page, when there is one (remembered on the account; nothing is charged).
 */
export const authRegister = (email: string, password: string, tick: TermsTick, choice: PlanChoice | null = null) =>
  call<void>('/auth/register', {
    method: 'POST', session: false,
    json: { email, password, acceptTerms: true, ...tick, ...(choice ? { plan: choice.plan, billing: choice.billing } : {}) },
  });

/** Confirms an address. It opens no session: the password does. The answer carries the plan chosen at registration, if any. */
export const authVerify = (token: string) =>
  call<PlanChoice | null>('/auth/verify', { method: 'POST', json: { token }, session: false },
    (raw) => (isRecord(raw) ? readPlanChoice(raw.plan, raw.billing) : null));

/** A signed-in account accepts the current texts (the re-prompt after a new version). */
export const acceptTerms = (tick: TermsTick) =>
  call<void>('/me/terms', { method: 'POST', json: tick });

export type SignInResult =
  | { kind: 'session'; session: string; expiresAt: string; isNew: boolean }
  /** Two-step sign-in is on: the ticket goes with the code to `authSecondStep`. */
  | { kind: 'second_step'; ticket: string };

function toSignIn(raw: unknown): SignInResult {
  if (isRecord(raw) && raw.secondStep === true && isTokenShaped(raw.ticket)) return { kind: 'second_step', ticket: raw.ticket };
  if (!isRecord(raw) || !isTokenShaped(raw.session)) throw new Error('bad session');
  return { kind: 'session', session: raw.session, expiresAt: typeof raw.expiresAt === 'string' ? raw.expiresAt : '', isNew: raw.isNew === true };
}

export const authLogin = (email: string, password: string) =>
  call<SignInResult>('/auth/login', { method: 'POST', json: { email, password }, session: false }, toSignIn);
export const authSecondStep = (ticket: string, code: string) =>
  call<SignInResult>('/auth/login/second', { method: 'POST', json: { ticket, code }, session: false }, toSignIn);

/** 202 whether or not the address has an account. */
export const resetRequest = (email: string) =>
  call<void>('/auth/reset/request', { method: 'POST', json: { email }, session: false });
export const resetConfirm = (token: string, password: string) =>
  call<void>('/auth/reset/confirm', { method: 'POST', json: { token, password }, session: false });

/* ---- password and two-step sign-in, signed in ---- */

export const changePassword = (currentPassword: string, newPassword: string) =>
  call<void>('/me/password', { method: 'POST', json: { currentPassword, newPassword } });

export interface TotpSetup { secret: string; uri: string }
export const totpSetup = (password: string) =>
  call<TotpSetup>('/me/totp/setup', { method: 'POST', json: { password } }, (raw) => {
    if (!isRecord(raw) || typeof raw.secret !== 'string' || typeof raw.uri !== 'string') throw new Error('bad setup');
    return { secret: raw.secret, uri: raw.uri };
  });
export const totpEnable = (code: string) =>
  call<string[]>('/me/totp/enable', { method: 'POST', json: { code } }, (raw) => {
    const codes = isRecord(raw) ? arr<unknown>(raw.recoveryCodes) : [];
    if (codes.length === 0 || !codes.every((c) => typeof c === 'string')) throw new Error('bad codes');
    return codes as string[];
  });
export const totpDisable = (password: string) =>
  call<void>('/me/totp/disable', { method: 'POST', json: { password } });

export const authLogout = () => call<void>('/auth/logout', { method: 'POST' });

/* ---- account ---- */

export const getMe = () => call<Me>('/me', {}, toMe);
export const updateMe = (patch: Partial<Profile>) => call<Me>('/me', { method: 'PATCH', json: patch }, toMe);
/** WP-123: the typed address and, for an account with a password, the password. */
export const deleteMe = (confirm: string, password: string) =>
  call<void>('/me', { method: 'DELETE', json: password ? { confirm, password } : { confirm } });

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

/** WP-157: `client`, only the searches of that client profile. */
export const listSearches = (client?: string | null) =>
  call<SavedSearch[]>(`/searches${client ? `?client=${encodeURIComponent(client)}` : ''}`, {}, (raw) => items<SavedSearch>(raw));
export const createSearch = (s: { name: string; kind: SearchKind; filters: SearchFilters; cadence?: Cadence }) =>
  call<SavedSearch>('/searches', { method: 'POST', json: s });
export const updateSearch = (id: string, patch: { name?: string; cadence?: Cadence; clientId?: string | null }) =>
  call<SavedSearch>(`/searches/${encodeURIComponent(id)}`, { method: 'PATCH', json: patch });
export const deleteSearch = (id: string) => call<void>(`/searches/${encodeURIComponent(id)}`, { method: 'DELETE' });

/* ---- shortlist and follows ---- */

export const listShortlist = (client?: string | null) =>
  call<ShortlistItem[]>(`/shortlist${client ? `?client=${encodeURIComponent(client)}` : ''}`, {}, (raw) => items<ShortlistItem>(raw));
/** WP-157: `clientId` left out keeps the entry's client profile, null takes it off. */
export const putShortlist = (kind: ShortlistKind, ref: string, status: ShortlistStatus, note: string, clientId?: string | null) =>
  call<ShortlistItem | null>(`/shortlist/${kind}/${encodeURIComponent(ref)}`,
    { method: 'PUT', json: clientId === undefined ? { status, note } : { status, note, clientId } });
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

/* ---- billing (WP-124): Creem, merchant of record ---- */

const toPlan = (v: unknown): PlanId => (typeof v === 'string' && Object.hasOwn(PLAN_LABELS, v) ? (v as PlanId) : 'free');
const toFeatures = (v: unknown): Feature[] => arr<unknown>(v).filter((f): f is Feature => (PAID_FEATURES as readonly unknown[]).includes(f));

export interface BillingState {
  open: boolean;
  testMode: boolean;
  plan: PlanId;
  features: Feature[];
  subscription: { plan: PlanId; period: Billing; status: string; periodEnd: string | null; refundedAt: string | null; canManage: boolean } | null;
  /** Founding customer places left: only while billing is open, and then true at the time of the request. */
  foundingLeft: number | null;
  foundingCap: number;
}

function toBilling(raw: unknown): BillingState {
  if (!isRecord(raw)) throw new Error('bad billing');
  const s = isRecord(raw.subscription) ? raw.subscription : null;
  const text = (v: unknown) => (typeof v === 'string' ? v : null);
  return {
    open: raw.open === true,
    testMode: raw.testMode !== false,
    plan: toPlan(raw.plan),
    features: toFeatures(raw.features),
    subscription: s ? {
      plan: toPlan(s.plan), period: s.period === 'yearly' ? 'yearly' : 'monthly', status: text(s.status)?.slice(0, 32) ?? 'unknown',
      periodEnd: text(s.periodEnd), refundedAt: text(s.refundedAt), canManage: s.canManage === true,
    } : null,
    foundingLeft: typeof raw.foundingLeft === 'number' ? raw.foundingLeft : null,
    foundingCap: typeof raw.foundingCap === 'number' ? raw.foundingCap : 20,
  };
}

export const getBilling = () => call<BillingState>('/billing', {}, toBilling);

/**
 * The address of Creem's hosted page, checked again here before the browser is sent to it: https on creem.io, or the origin of the
 * e2e test's local stand-in (DG_E2E_CREEM_ORIGIN, set only by that test, never in infra/docker-compose.yml).
 */
function providerUrl(raw: unknown): string {
  const v = isRecord(raw) ? raw.url : null;
  if (typeof v !== 'string') throw new Error('bad url');
  const u = new URL(v);
  const creem = u.protocol === 'https:' && !u.username && !u.password && (u.hostname === 'creem.io' || u.hostname.endsWith('.creem.io'));
  if (!creem && !(process.env.DG_E2E_CREEM_ORIGIN && u.origin === process.env.DG_E2E_CREEM_ORIGIN)) throw new Error('bad url');
  return u.toString();
}

/** A Creem checkout for this account, created by the API (the key never reaches the browser). */
export const createCheckout = (plan: Exclude<PlanId, 'free'>, billing: Billing) =>
  call<string>('/billing/checkout', { method: 'POST', json: { plan, billing } }, providerUrl);
/** Creem's customer portal of this account: cancel, invoices, payment method. */
export const openPortal = () => call<string>('/billing/portal', { method: 'POST' }, providerUrl);

/* ---- keys of the data API (WP-153) ---- */

const KEY_SCOPES = ['tenders', 'archive'] as const;
const text = (v: unknown, max = 100): string => (typeof v === 'string' ? v.slice(0, max) : '');
const stamp = (v: unknown): string | null => (typeof v === 'string' ? v.slice(0, 40) : null);
const count = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0);

function toApiKey(raw: unknown): ApiKey {
  if (!isRecord(raw) || typeof raw.id !== 'string') throw new Error('bad key');
  return {
    id: raw.id, name: text(raw.name, 60), prefix: text(raw.prefix, 12),
    scopes: arr<unknown>(raw.scopes).map((s) => oneOf(s, KEY_SCOPES)).filter((s): s is ApiKey['scopes'][number] => s !== null),
    ratePerMinute: count(raw.ratePerMinute), dailyQuota: count(raw.dailyQuota),
    createdAt: stamp(raw.createdAt) ?? '', expiresAt: stamp(raw.expiresAt) ?? '',
    lastUsedAt: stamp(raw.lastUsedAt), revokedAt: stamp(raw.revokedAt), requestsToday: count(raw.requestsToday),
  };
}

function toApiKeys(raw: unknown): ApiKeys {
  if (!isRecord(raw)) throw new Error('bad keys');
  return {
    open: raw.open === true,
    // WP-155: keys need the data licence (the operator grants it); an answer without the field is read as licensed
    licensed: raw.licensed !== false,
    sources: arr<unknown>(raw.sources).filter((s): s is string => typeof s === 'string').map((s) => s.slice(0, 32)),
    maxKeys: count(raw.maxKeys),
    keys: arr<unknown>(raw.keys).map(toApiKey),
    events: arr<unknown>(raw.events).filter(isRecord).map((e) => ({
      event: e.event === 'revoked' ? 'revoked' : 'created', at: stamp(e.at) ?? '', name: text(e.name, 60), prefix: text(e.prefix, 12),
    })),
  };
}

export const listApiKeys = () => call<ApiKeys>('/keys', {}, toApiKeys);
/** The answer carries the key itself, once: it is shown on the page that asked and never stored by the site. */
export const createApiKey = (name: string, scopes: ApiKey['scopes'], password: string) =>
  call<{ key: string; meta: ApiKey }>('/keys', { method: 'POST', json: { name, scopes, password } }, (raw) => {
    const key = isRecord(raw) ? raw.key : null;
    if (typeof key !== 'string' || !/^dgk_[0-9a-f]{12}_[A-Za-z0-9_-]{43}$/.test(key)) throw new Error('bad key');
    return { key, meta: toApiKey(raw) };
  });
export const revokeApiKey = (id: string, password: string) =>
  call<ApiKey>(`/keys/${encodeURIComponent(id)}/revoke`, { method: 'POST', json: { password } }, toApiKey);

/* ---- the association of a cluster licence and its digest (WP-158) ---- */

function toAssociation(raw: unknown): AssociationView {
  if (!isRecord(raw) || typeof raw.name !== 'string') throw new Error('bad association');
  const d = isRecord(raw.digest) ? raw.digest : {};
  const s = isRecord(raw.seats) ? raw.seats : null;
  return {
    name: text(raw.name, 80), role: raw.role === 'admin' ? 'admin' : 'member', plan: raw.plan === 'team' ? 'team' : 'pro',
    memberSince: stamp(raw.memberSince) ?? '', licensedUntil: stamp(raw.licensedUntil),
    digest: {
      on: d.on === true,
      country: typeof d.country === 'string' && /^[A-Z]{2}$/.test(d.country) ? d.country : null,
      cpv: arr<unknown>(d.cpv).filter((c): c is string => typeof c === 'string' && /^[0-9]{2,8}$/.test(c)),
      lastWeek: typeof d.lastWeek === 'string' ? d.lastWeek.slice(0, 8) : null,
    },
    seats: s ? { used: count(s.used), cap: count(s.cap) } : null,
  };
}

export const getAssociation = () => call<AssociationView>('/association', {}, toAssociation);
export const setAssociationDigest = (digest: { on: boolean; country: string | null; cpv: string[] }) =>
  call<AssociationView>('/association/digest', { method: 'PUT', json: digest }, toAssociation);
/** The link in a digest mail: no session, the token alone switches that mail off. */
export const unsubscribeDigest = (token: string) =>
  call<{ done: boolean }>('/association/unsubscribe', { method: 'POST', session: false, json: { token } });
/** WP-161: the stop link of a saved-search alert mail (no sign-in): every alert of that account off. */
export const unsubscribeAlerts = (token: string) =>
  call<{ done: boolean }>('/alerts/unsubscribe', { method: 'POST', session: false, json: { token } });

/* ---- dashboard ---- */

/** Also moves the account's lastVisitAt: the API does that on this call only. */
export const getDashboard = () => call<Dashboard>('/dashboard', {}, toDashboard);

/* ---- WP-154: company signals, the paid part (the whole list a page at a time; the CSV asks for CSV_ROWS at once) ---- */

/**
 * WP-155: the first rows of a signal as they rank, the small companies' with them (the public answer leaves those out): any
 * signed-in account's.
 */
export const getFirstSignal = (f: Omit<SignalFilters, 'page'>) => {
  const q = signalQuery(f);
  return call<SignalAnswer>(`/signals/${f.kind}/first${q ? `?${q}` : ''}`, {}, (raw) => {
    if (!isRecord(raw) || !Array.isArray(raw.items)) throw new Error('bad signals');
    return raw as unknown as SignalAnswer;
  });
};

/* ---- WP-155: a company's whole competitor list, and a company report opened (counted per company and month) ---- */

/** 402 without a plan that has the full list (once plans are on sale), 401 signed out. */
export const getFullCompetition = (slug: string) =>
  call<SupplierCompetition>(`/suppliers/${encodeURIComponent(slug)}/competition`, {}, (raw) => {
    if (!isRecord(raw) || typeof raw.available !== 'boolean') throw new Error('bad competition');
    return { ...(raw as unknown as SupplierCompetition), competitors: arr(raw.competitors) };
  });

export interface ReportOpening {
  sample: boolean;
  counted: boolean;
  used: number | null;
  /** Reports a month on the plan; null: no limit. */
  limit: number | null;
  left: number | null;
  /** The first day of next month (UTC), when the count starts again. */
  resetsAt: string;
  /** The account's own name for the report's head (Consultant), plain text. */
  reportName: string | null;
  /** WP-157: the client profile's name for the report's head (Consultant, asked with `client`), plain text. */
  clientName?: string | null;
}

/** 402 `plan_required` without a plan that has reports, 402 `report_quota` when this month's are used (the message says when they renew). */
export const openReport = (slug: string, client?: string | null) =>
  call<ReportOpening>(`/suppliers/${encodeURIComponent(slug)}/report${client ? `?client=${encodeURIComponent(client)}` : ''}`, { method: 'POST' }, (raw) => {
    if (!isRecord(raw)) throw new Error('bad report');
    const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
    return {
      sample: raw.sample === true, counted: raw.counted === true, used: n(raw.used), limit: n(raw.limit), left: n(raw.left),
      resetsAt: typeof raw.resetsAt === 'string' ? raw.resetsAt.slice(0, 10) : '',
      reportName: typeof raw.reportName === 'string' ? raw.reportName.slice(0, 80) : null,
      clientName: typeof raw.clientName === 'string' ? raw.clientName.slice(0, 120) : null,
    };
  });

/** 404 `not_open` while DGATE_SIGNALS_FULL_OPEN is off, 402 without a plan that includes it, 401 signed out (lib/signals fullState). */

export const getFullSignal = (f: Omit<SignalFilters, 'page'>, page: number, pageSize: number) => {
  const q = signalQuery(f);
  return call<SignalAnswer>(`/signals/${f.kind}?${q ? `${q}&` : ''}page=${page}&pageSize=${pageSize}`, {}, (raw) => {
    if (!isRecord(raw) || !Array.isArray(raw.items)) throw new Error('bad signals');
    return raw as unknown as SignalAnswer;
  });
};

/* ---- WP-156: the two exports (backend exports.py); 402 `plan_required` without the feature, 401 signed out ---- */

export interface SupplierExport { items: SupplierItem[]; total: number; cap: number; placsp: boolean; asOf: string }

/** The supplier map's list under its filters (the API's own names and values, as getSuppliers sends them), up to `cap` rows. */
export const getSupplierExport = (f: SupplierFilters) => {
  const p = new URLSearchParams();
  for (const k of ['q', 'country', 'buyerCountry', 'cpv', 'group', 'source'] as const) if (f[k]) p.set(k, String(f[k]));
  if (f.sort && f.sort !== 'awards') p.set('sort', f.sort);
  return call<SupplierExport>(`/suppliers/export${p.size ? `?${p.toString()}` : ''}`, { timeoutMs: 60_000 }, (raw) => {
    if (!isRecord(raw) || !Array.isArray(raw.items) || typeof raw.total !== 'number') throw new Error('bad export');
    return raw as unknown as SupplierExport;
  });
};

/** Every open call with the facts the eligibility check compares: the same for every account; the profile never leaves the browser. */
export const getEligibilityCalls = () =>
  call<PackAnswer>('/eligibility/calls', { timeoutMs: 30_000 }, (raw) => {
    if (!isRecord(raw) || !Array.isArray(raw.items) || typeof raw.total !== 'number') throw new Error('bad calls');
    return raw as unknown as PackAnswer;
  });

/* ---- WP-160: contracts ending soon, the paid part (Pro: the whole list a page at a time; Team: the CSV, CSV_ROWS at once) ---- */

/** 402 without a plan that has it (once plans are on sale), 401 signed out (lib/contract-period endingState). */
export const getFullEnding = (f: Omit<EndingFilters, 'page'>, page: number, pageSize: number) => {
  const q = endingQuery(f);
  return call<EndingAnswer>(`/contracts/ending?${q ? `${q}&` : ''}page=${page}&pageSize=${pageSize}`, { timeoutMs: pageSize > 100 ? 60_000 : 10_000 }, (raw) => {
    if (!isRecord(raw) || !Array.isArray(raw.items) || typeof raw.total !== 'number') throw new Error('bad ending');
    return raw as unknown as EndingAnswer;
  });
};
