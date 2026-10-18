/**
 * The fit of the calls on a page to the saved profile, held in the browser (WP-32). Client only.
 *
 * The page is rendered, cached and served the same for everybody. A visitor with a saved profile
 * (`dg.profile.v1`, see lib/profile.ts) gets a badge per call on top of it, computed here:
 *
 *   1. each badge or list item on the page calls `mount(id)` from an effect, which does nothing at all when the
 *      browser holds no profile (no request, no work: a visitor without a profile costs the server nothing);
 *   2. with a profile, the ids of the page are collected for a few milliseconds and asked for in one request,
 *      `GET /api/fit/facts?ids=...`: only public ids go out, never the profile;
 *   3. for calls of a programme that has readiness rules (EDF, EDIP), the profile's verdict for the programmes is
 *      asked once per profile, `POST /api/readiness/assess`, the request the readiness pages make;
 *   4. the facts and the programme verdict are compared with the profile by lib/fit.ts and the badges re-render.
 *
 * The React hooks are in lib/fit-hooks.ts (this file has no import of React, so lib/fit-store.check.ts can run it in node).
 * `useSyncExternalStore` keeps the first client render equal to the server's (no badge, nothing hidden), so there
 * is no hydration mismatch; badges appear after hydration. The profile is read again every time an item mounts,
 * so a profile changed on /readiness is seen after a client-side navigation.
 */
import type { EligibilityFacts } from './eligibility-check';
import { fitOf, fitsProfile, programmeFit, programmesOfCall, withProgramme, type Fit, type FitResult } from './fit';
import { PROFILE_KEY, loadProfile, toRequest, type Profile } from './profile';
import { assess } from './readiness';
import type { Assessment } from './readiness-types';

interface Entry { state: 'read' | 'not_read' | 'no_source'; facts: EligibilityFacts; programme: string; topic: string }

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
/** The programmes' verdict for the profile: `settled` once it came or failed. A new object per profile. */
let programmes: { data: Assessment | null; settled: boolean; asked: boolean } = { data: null, settled: false, asked: false };
const mounted = new Map<string, number>();         // id -> items on the page showing it
const entries = new Map<string, Entry | null>();   // null: asked and nothing came back
const asked = new Set<string>();
let queue: string[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

const hasProfile = (): boolean => profile !== null && profile.country !== '';

function codesOf(id: string): string[] {
  const e = entries.get(id);
  return e ? programmesOfCall(e.programme, e.topic) : [];
}

/** The fit of one call to the saved profile; `unknown` while its facts have not come. */
export function fitFor(id: string): FitResult {
  const entry = entries.get(id);
  const doc: FitResult = entry && entry.state === 'read' ? fitOf(entry.facts, profile) : { fit: 'unknown', result: null, conditions: [] };
  return withProgramme(doc, programmeFit(programmes.data, codesOf(id)));
}

/**
 * Whether the badge of a call can be shown: its facts have been looked up and, if its programme has rules, the
 * profile's verdict for the programmes has come or failed (so a badge does not change from "check" to "not eligible").
 */
export function isLoaded(id: string): boolean {
  return entries.has(id) && (programmes.settled || codesOf(id).length === 0);
}

function recount(): void {
  const counts: Record<Fit, number> = { yes: 0, check: 0, no: 0, unknown: 0 };
  let loaded = 0;
  for (const id of mounted.keys()) {
    if (!isLoaded(id)) continue;
    loaded += 1;
    counts[fitFor(id).fit] += 1;
  }
  snapshot = { ready: true, hasProfile: hasProfile(), onlyFits, counts, loaded, version: snapshot.version + 1 };
  for (const l of listeners) l();
}

function readProfile(): boolean {
  let raw: string | null = null;
  try { raw = window.localStorage.getItem(PROFILE_KEY); } catch { /* blocked storage: no profile */ }
  if (snapshot.ready && raw === rawProfile) return false;
  rawProfile = raw;
  profile = raw === null ? null : loadProfile();
  programmes = { data: null, settled: false, asked: false };        // another profile, another verdict
  return true;
}

/** The profile's verdict for the programmes, asked once, when a call of a programme with rules is on the page. */
function ensureProgrammes(): void {
  if (programmes.asked || !profile || !hasProfile()) return;
  if (![...entries.keys()].some((id) => codesOf(id).length > 0)) return;
  const request = toRequest(profile);
  if (!request) return;
  const mine = { data: null as Assessment | null, settled: false, asked: true };
  programmes = mine;
  assess(request).then(
    (data) => { if (programmes === mine) { programmes = { data, settled: true, asked: true }; recount(); } },
    // No programme verdict: the document alone speaks, and the badge says nothing the document does not.
    () => { if (programmes === mine) { programmes = { data: null, settled: true, asked: true }; recount(); } },
  );
}

async function flush(): Promise<void> {
  timer = null;
  while (queue.length > 0) {
    const ids = queue.splice(0, MAX_IDS);
    try {
      const res = await fetch(`/api/fit/facts?ids=${ids.join(',')}`, { headers: { accept: 'application/json' }, credentials: 'omit' });
      if (!res.ok) throw new Error(String(res.status));
      const body = (await res.json()) as { items?: Record<string, {
        state: Entry['state']; programme?: string; topic?: string; facts?: Record<string, { value: unknown; note?: string | null; scope?: string }>;
      }> };
      for (const id of ids) {
        const item = body.items?.[id];
        entries.set(id, item ? {
          state: item.state, programme: item.programme ?? '', topic: item.topic ?? '',
          facts: Object.fromEntries(Object.entries(item.facts ?? {}).map(([k, v]) => [k, { value: v.value, note: v.note ?? null, quote: '', confidence: 1, scope: v.scope as 'call_document' | 'general' | 'topic' | undefined }])),
        } : null);
      }
    } catch {
      // The badge stays "unknown": a failed look-up is never read as a verdict. A later page asks again.
      for (const id of ids) { asked.delete(id); entries.set(id, null); }
    }
    ensureProgrammes();
    recount();
  }
}

/** An item showing call `id` is on the page: read the profile, and with one, ask for the call's facts. */
export function mount(id: string): void {
  mounted.set(id, (mounted.get(id) ?? 0) + 1);
  const changed = readProfile();
  if (hasProfile() && !asked.has(id)) {
    asked.add(id);
    queue.push(id);
    if (timer === null) timer = setTimeout(() => { void flush(); }, WAIT_MS);
  }
  if (changed) {
    ensureProgrammes();      // another profile: the facts held stay good, the programmes' verdict is asked again
    recount();
  }
}

export function unmount(id: string): void {
  const n = (mounted.get(id) ?? 1) - 1;
  if (n <= 0) mounted.delete(id); else mounted.set(id, n);
  if (mounted.size === 0 && onlyFits) onlyFits = false;      // leaving the list turns the filter off
  recount();
}

export function setOnlyFits(value: boolean): void {
  onlyFits = value;
  recount();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export const getSnapshot = (): FitSnapshot => snapshot;
export const getServerSnapshot = (): FitSnapshot => SERVER;

/** Read the profile again (the hook of the filter calls it once on mount). */
export function refresh(): void {
  if (readProfile()) recount();
}

/** An item is hidden by "Fits my profile" when its facts are in and it is neither eligible nor worth a look. */
export function hiddenByFilter(s: FitSnapshot, id: string): boolean {
  return s.onlyFits && s.hasProfile && isLoaded(id) && !fitsProfile(fitFor(id).fit);
}
