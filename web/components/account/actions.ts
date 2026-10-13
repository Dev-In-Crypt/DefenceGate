'use server';

/**
 * Server actions behind the save and follow islands on public pages. Each is a public POST endpoint, so every
 * argument is checked here before it reaches the API. A 401 clears the session cookie (actions may set cookies).
 */
import {
  clearCookie, createSearch, deleteFollow, deleteShortlist, getState, putFollow, putShortlist, readSession, SESSION_COOKIE,
  type AccountResult,
} from '@/lib/account';
import { FILTER_KEYS } from '@/lib/account-format';
import { followRef, numericRef } from '@/lib/refs';
import type { FollowKind, SearchFilters, SearchKind, ShortlistKind, StateItem, StateKey } from '@/lib/types';

export type SnapshotMode = 'anonymous' | 'ready' | 'unavailable';
export interface Snapshot { mode: SnapshotMode; items: StateItem[] }
export interface ActionOutcome {
  ok: boolean;
  mode: SnapshotMode;
  /** The state after the action (save, follow). */
  on?: boolean;
  /** Plain words for the visitor when `ok` is false. */
  message?: string;
}

const MAX_KEYS = 50;

function cleanKey(k: unknown): StateKey | null {
  if (typeof k !== 'object' || k === null) return null;
  const { type, kind, ref } = k as Record<string, unknown>;
  if (typeof ref !== 'string') return null;
  // The reference is normalised here, once: digits without leading zeros for an id, so `007` and `7` are one item.
  if (type === 'shortlist' && (kind === 'tender' || kind === 'call')) {
    const r = numericRef(ref);
    return r === null ? null : { type, kind, ref: r };
  }
  if (type === 'follow' && (kind === 'buyer' || kind === 'programme')) {
    const r = followRef(kind, ref);
    return r === null ? null : { type, kind, ref: r };
  }
  return null;
}

async function dropSession(): Promise<void> {
  await clearCookie(SESSION_COOKIE);
}

/** Maps a failed call to what the island shows. A 401 means the session is gone: the cookie goes with it. */
async function failed(r: Extract<AccountResult<unknown>, { ok: false }>, fallback: string): Promise<ActionOutcome> {
  if (r.status === 401) {
    await dropSession();
    return { ok: false, mode: 'anonymous' };
  }
  if (r.status === 429) return { ok: false, mode: 'ready', message: 'Too many requests. Try again later.' };
  return { ok: false, mode: r.status === 0 || r.status >= 500 ? 'unavailable' : 'ready', message: r.message ?? fallback };
}

/**
 * What the account has saved among `keys` (one call for all islands on a page). Without a session cookie
 * nothing is sent to the API. With no keys it only reports whether a session exists.
 */
export async function accountSnapshot(keys: StateKey[]): Promise<Snapshot> {
  if (!(await readSession())) return { mode: 'anonymous', items: [] };
  const clean = (Array.isArray(keys) ? keys : []).slice(0, MAX_KEYS).map(cleanKey).filter((k): k is StateKey => k !== null);
  if (clean.length === 0) return { mode: 'ready', items: [] };
  const r = await getState(clean);
  if (r.ok) return { mode: 'ready', items: r.data };
  if (r.status === 401) {
    await dropSession();
    return { mode: 'anonymous', items: [] };
  }
  return { mode: 'unavailable', items: [] };
}

export async function setShortlisted(kind: ShortlistKind, ref: string, on: boolean): Promise<ActionOutcome> {
  const key = cleanKey({ type: 'shortlist', kind, ref });
  if (!key) return { ok: false, mode: 'ready', message: 'That item cannot be saved.' };
  const r = on ? await putShortlist(kind, key.ref, 'watching', '') : await deleteShortlist(kind, key.ref);
  if (r.ok || (!on && r.status === 404)) return { ok: true, mode: 'ready', on };
  return failed(r, 'Could not update your shortlist.');
}

export async function setFollowed(kind: FollowKind, ref: string, on: boolean): Promise<ActionOutcome> {
  const key = cleanKey({ type: 'follow', kind, ref });
  if (!key) return { ok: false, mode: 'ready', message: 'That cannot be followed.' };
  const r = on ? await putFollow(kind, key.ref) : await deleteFollow(kind, key.ref);
  if (r.ok || (!on && r.status === 404)) return { ok: true, mode: 'ready', on };
  return failed(r, 'Could not update what you follow.');
}

/** `filters` are the list page's own query keys; anything else is dropped before the API sees it. */
export async function saveSearch(kind: SearchKind, name: string, filters: SearchFilters): Promise<ActionOutcome> {
  if (kind !== 'tender' && kind !== 'call') return { ok: false, mode: 'ready', message: 'Could not save this search.' };
  const clean: SearchFilters = {};
  for (const key of FILTER_KEYS[kind]) {
    const v = (filters as Record<string, unknown> | null)?.[key];
    if (typeof v === 'string' && v.length > 0 && v.length <= 200) clean[key] = v;
  }
  const title = typeof name === 'string' ? name.trim().slice(0, 80) : '';
  if (!title) return { ok: false, mode: 'ready', message: 'Give the search a name.' };
  const r = await createSearch({ name: title, kind, filters: clean });
  if (r.ok) return { ok: true, mode: 'ready' };
  return failed(r, 'Could not save this search. You may have reached the limit of 25 saved searches.');
}
