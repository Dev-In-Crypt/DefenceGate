/**
 * The fit of the calls on a page to the saved profile, held in the browser (WP-32). Client only.
 *
 * The page is rendered, cached and served the same for everybody. A visitor with a saved profile
 * (`dg.profile.v1`, see lib/profile.ts) gets a badge per call on top of it, computed here:
 *
 *   1. each badge or list item on the page calls `track(id)` from an effect, which does nothing at all when the
 *      browser holds no profile (no request, no work: a visitor without a profile costs the server nothing);
 *   2. with a profile, the ids of the page are collected for a few milliseconds and asked for in one request,
 *      `GET /api/fit/facts?ids=...`: only public ids go out, never the profile;
 *   3. the facts are compared with the profile by lib/fit.ts and the badges re-render.
 *
 * `useSyncExternalStore` keeps the first client render equal to the server's (no badge, nothing hidden), so there
 * is no hydration mismatch; badges appear after hydration. The profile is read again every time an item mounts,
 * so a profile changed on /readiness is seen after a client-side navigation.
 */
import { useEffect, useSyncExternalStore } from 'react';
import type { EligibilityFacts } from './eligibility-check';
import { fitOf, fitsProfile, type Fit, type FitResult } from './fit';
import { PROFILE_KEY, loadProfile, type Profile } from './profile';

interface Entry { state: 'read' | 'not_read' | 'no_source'; facts: EligibilityFacts }

export interface FitSnapshot {
  /** The browser has been asked for its profile (false on the server and for the first client render). */
  ready: boolean;
  hasProfile: boolean;
  /** "Fits my profile" is on. */
  onlyFits: boolean;
  /** Calls on the page by verdict, once their facts are in. */
  counts: Record<Fit, number>;
  loaded: number;
  version: number;
}

const EMPTY_COUNTS: Record<Fit, number> = { yes: 0, check: 0, no: 0, unknown: 0 };
const SERVER: FitSnapshot = { ready: false, hasProfile: false, onlyFits: false, counts: EMPTY_COUNTS, loaded: 0, version: 0 };

const MAX_IDS = 100;
const WAIT_MS = 40;

let snapshot: FitSnapshot = SERVER;
let profile: Profile | null = null;
let rawProfile: string | null = null;
let onlyFits = false;
const mounted = new Map<string, number>();         // id -> items on the page showing it
const entries = new Map<string, Entry | null>();   // null: asked and nothing came back
const asked = new Set<string>();
let queue: string[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

function recount(): void {
  const counts: Record<Fit, number> = { yes: 0, check: 0, no: 0, unknown: 0 };
  let loaded = 0;
  for (const id of mounted.keys()) {
    if (!entries.has(id)) continue;
    loaded += 1;
    counts[fitFor(id).fit] += 1;
  }
  snapshot = { ready: true, hasProfile: profile !== null && profile.country !== '', onlyFits, counts, loaded, version: snapshot.version + 1 };
  for (const l of listeners) l();
}

function readProfile(): boolean {
  let raw: string | null = null;
  try { raw = window.localStorage.getItem(PROFILE_KEY); } catch { /* blocked storage: no profile */ }
  if (snapshot.ready && raw === rawProfile) return false;
  rawProfile = raw;
  profile = raw === null ? null : loadProfile();
  return true;
}

/** The fit of one call to the saved profile; `unknown` while its facts have not come. */
export function fitFor(id: string): FitResult {
  const entry = entries.get(id);
  if (!entry || entry.state !== 'read') return { fit: 'unknown', result: null };
  return fitOf(entry.facts, profile);
}

/** Whether the facts of a call have been looked up (so "unknown" means "nothing to compare", not "not yet"). */
export function isLoaded(id: string): boolean {
  return entries.has(id);
}

async function flush(): Promise<void> {
  timer = null;
  while (queue.length > 0) {
    const ids = queue.splice(0, MAX_IDS);
    try {
      const res = await fetch(`/api/fit/facts?ids=${ids.join(',')}`, { headers: { accept: 'application/json' }, credentials: 'omit' });
      if (!res.ok) throw new Error(String(res.status));
      const body = (await res.json()) as { items?: Record<string, { state: Entry['state']; facts?: Record<string, { value: unknown; note?: string | null; scope?: string }> }> };
      for (const id of ids) {
        const item = body.items?.[id];
        entries.set(id, item ? {
          state: item.state,
          facts: Object.fromEntries(Object.entries(item.facts ?? {}).map(([k, v]) => [k, { value: v.value, note: v.note ?? null, quote: '', confidence: 1, scope: v.scope as 'call_document' | 'general' | 'topic' | undefined }])),
        } : null);
      }
    } catch {
      // The badge stays "unknown": a failed look-up is never read as a verdict. A later page asks again.
      for (const id of ids) asked.delete(id);
      for (const id of ids) entries.set(id, null);
    }
    recount();
  }
}

/** An item showing call `id` is on the page: read the profile, and with one, ask for the call's facts. */
function mount(id: string): void {
  mounted.set(id, (mounted.get(id) ?? 0) + 1);
  const changed = readProfile();
  if (profile !== null && profile.country !== '' && !asked.has(id)) {
    asked.add(id);
    queue.push(id);
    if (timer === null) timer = setTimeout(() => { void flush(); }, WAIT_MS);
  }
  if (changed) recount();
}

function unmount(id: string): void {
  const n = (mounted.get(id) ?? 1) - 1;
  if (n <= 0) mounted.delete(id); else mounted.set(id, n);
  if (mounted.size === 0 && onlyFits) onlyFits = false;      // leaving the list turns the filter off
  recount();
}

export function setOnlyFits(value: boolean): void {
  onlyFits = value;
  recount();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
const getSnapshot = (): FitSnapshot => snapshot;
const getServerSnapshot = (): FitSnapshot => SERVER;

/** For a badge or an item of a list: the state of the store, with the item registered while it is on the page. */
export function useFit(id: string): FitSnapshot {
  useEffect(() => {
    mount(id);
    return () => unmount(id);
  }, [id]);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** For the filter: the state of the store, with no call registered. */
export function useFitState(): FitSnapshot {
  useEffect(() => {
    if (readProfile()) recount();
  }, []);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** An item is hidden by "Fits my profile" when its facts are in and it is neither eligible nor worth a look. */
export function hiddenByFilter(s: FitSnapshot, id: string): boolean {
  return s.onlyFits && s.hasProfile && isLoaded(id) && !fitsProfile(fitFor(id).fit);
}
