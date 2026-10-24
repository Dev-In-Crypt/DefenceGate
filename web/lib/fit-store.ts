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
import type { EligibilityFact, EligibilityFacts } from './eligibility-check';
import { callFit, fitsProfile, programmesOfCall, shownFit, type Fit, type FitResult } from './fit';
import { PROFILE_KEY, loadProfile, toRequest, type Profile } from './profile';
import { assess } from './readiness';
import { topicScore, topicWords } from './funding-path';
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
  /** WP-91: the topics of the saved profile (`Profile.topics`, folded): "Fits my profile" lists the calls that hold most of them first. */
  topics: string[];
}

const EMPTY_COUNTS: Record<Fit, number> = { yes: 0, check: 0, no: 0, unknown: 0 };
const SERVER: FitSnapshot = { ready: false, hasProfile: false, onlyFits: false, counts: EMPTY_COUNTS, loaded: 0, version: 0, topics: [] };

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
/** WP-102 (BM-01 69): calls whose look-up failed (a 429 or a network error): never shown as "rules not read". Asked once more after RETRY_MS. */
const failed = new Set<string>();
const retried = new Set<string>();
const RETRY_MS = 4000;
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
  // WP-93: the one verdict (lib/fit.ts `callFit`), the same on the call page
  return callFit(entries.get(id) ?? null, profile, programmes.data);
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
    counts[shownFit(fitFor(id))] += 1;      // a "yes" that carries a condition counts, and is shown, as "conditions to check"
  }
  snapshot = { ready: true, hasProfile: hasProfile(), onlyFits, counts, loaded, version: snapshot.version + 1, topics: topicWords(profile?.topics ?? '') };
  for (const l of listeners) l();
}

function readProfile(): boolean {
  let raw: string | null = null;
  try { raw = window.localStorage.getItem(PROFILE_KEY); } catch { /* blocked storage: no profile */ }
  if (snapshot.ready && raw === rawProfile) return false;
  rawProfile = raw;
  const before = profile;
  profile = raw === null ? null : loadProfile();
  // another profile, another verdict; a change of the topics alone (WP-91) or of the date changes no rule's answer
  const same = (p: Profile | null) => (p ? JSON.stringify({ ...p, topics: '', updatedAt: null }) : null);
  if (!snapshot.ready || same(before) !== same(profile)) programmes = { data: null, settled: false, asked: false };
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
        state: Entry['state']; programme?: string; topic?: string; facts?: Record<string, { value: unknown; note?: string | null; quote?: string | null; scope?: string }>;
      }> };
      for (const id of ids) {
        failed.delete(id);
        const item = body.items?.[id];
        entries.set(id, item ? {
          state: item.state, programme: item.programme ?? '', topic: item.topic ?? '',
          // WP-93 (fix 5): the quote comes too, so that the badge reads the same sentence as the call page (call 45: "controlled by China")
          facts: Object.fromEntries(Object.entries(item.facts ?? {}).map(([k, v]) => [k, { value: v.value, note: v.note ?? null, quote: v.quote ?? '', confidence: 1, scope: v.scope as EligibilityFact['scope'] }])),
        } : null);
      }
    } catch {
      // The badge stays "unknown": a failed look-up is never read as a verdict. A later page asks again.
      for (const id of ids) { asked.delete(id); entries.set(id, null); failed.add(id); }
      const again = ids.filter((id) => !retried.has(id));
      for (const id of again) retried.add(id);
      if (again.length > 0) setTimeout(() => { for (const id of again) if (mounted.has(id) && !asked.has(id)) { asked.add(id); queue.push(id); } if (queue.length > 0 && timer === null) timer = setTimeout(() => { void flush(); }, WAIT_MS); }, RETRY_MS);
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

/** WP-91: how many of the profile's topics a call's text holds (0 without topics). */
export function topicsMatched(s: FitSnapshot, text: string): number {
  return s.topics.length > 0 ? topicScore(s.topics, text) : 0;
}

/** WP-102: the look-up of this call's facts failed (the badge and the call page say so instead of "rules not read"). */
export function lookupFailed(id: string): boolean {
  return failed.has(id);
}

/** An item is hidden by "Fits my profile" when its facts are in and it is neither eligible nor worth a look (a failed look-up hides nothing). */
export function hiddenByFilter(s: FitSnapshot, id: string): boolean {
  return s.onlyFits && s.hasProfile && isLoaded(id) && !failed.has(id) && !fitsProfile(fitFor(id).fit);
}
