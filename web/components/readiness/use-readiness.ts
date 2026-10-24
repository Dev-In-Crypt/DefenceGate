'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { clearProfile, emptyProfile, loadProfile, saveProfile, toRequest, type Profile } from '@/lib/profile';
import { ASSESS_FAILED, AssessError, assess } from '@/lib/readiness';
import type { Assessment } from '@/lib/readiness-types';
import { DEMAND_FAILED, DemandError, demandRequest, fetchDemand, type Demand } from '@/lib/demand';
import { recall, shared } from '@/lib/answer-cache';

/**
 * The profile of the visitor, from and to localStorage only. `ready` is false on the server and for the first
 * client render, so the page renders the same markup in both (no hydration mismatch) and then fills in.
 * `profile` is null until it is read, and an empty profile when there is none.
 */
export function useProfile() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [stored, setStored] = useState(true);
  const current = useRef<Profile | null>(null);
  useEffect(() => {
    current.current = loadProfile() ?? emptyProfile();
    setProfile(current.current);
  }, []);
  const update = useCallback((change: (p: Profile) => Profile) => {
    const next = change(current.current ?? emptyProfile());
    current.current = next;
    setProfile(next);
    setStored(saveProfile(next));
  }, []);
  const clear = useCallback(() => {
    clearProfile();
    current.current = emptyProfile();
    setProfile(current.current);
  }, []);
  return { profile, ready: profile !== null, update, clear, stored };
}

export type AssessState =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'done'; data: Assessment };

/**
 * Ask the API for the verdict of the profile whenever its answers change. Nothing is kept. `programmes` (WP-89): only these (the roadmap
 * of a supplier that does not want EU funding asks the supply routes); null for every one.
 */
export function useAssessment(profile: Profile | null, programmes: string[] | null = null): AssessState & { retry: () => void } {
  const [result, setResult] = useState<AssessState>({ state: 'idle' });
  const [attempt, setAttempt] = useState(0);
  const seq = useRef(0);
  const base = profile ? toRequest(profile) : null;
  const request = base && programmes ? { ...base, programmes } : base;
  const key = request ? JSON.stringify(request) : '';
  useEffect(() => {
    if (!key) {
      setResult({ state: 'idle' });
      return;
    }
    const controller = new AbortController();
    const mine = ++seq.current;
    // WP-105: the answer the results page got for these very answers, a moment ago, is not asked again (the API's rate limit)
    const kept = recall<Assessment>('assess', key);
    if (kept) {
      setResult({ state: 'done', data: kept });
      return;
    }
    setResult((r) => (r.state === 'done' ? r : { state: 'loading' }));
    // WP-112: not aborted when the page is left; the next page waits for the same request (`shared`)
    shared('assess', key, () => assess(JSON.parse(key))).then(
      (data) => { if (mine === seq.current && !controller.signal.aborted) setResult({ state: 'done', data }); },
      (e: unknown) => {
        if (controller.signal.aborted || mine !== seq.current) return;
        setResult({ state: 'error', message: e instanceof AssessError ? e.message : ASSESS_FAILED });
      },
    );
    return () => controller.abort();
  }, [key, attempt]);
  return { ...result, retry: () => setAttempt((n) => n + 1) };
}

export type DemandState =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'done'; data: Demand };

/** The demand map for the profile's CPV codes (WP-66), asked again only when the codes change; kept in the tab a few minutes (WP-105). */
export function useDemand(profile: Profile | null): DemandState & { retry: () => void } {
  const [result, setResult] = useState<DemandState>({ state: 'idle' });
  const [attempt, setAttempt] = useState(0);
  const request = profile ? demandRequest(profile) : null;
  const key = request ? JSON.stringify(request) : '';
  useEffect(() => {
    if (!key) {
      setResult({ state: 'idle' });
      return;
    }
    const controller = new AbortController();
    const kept = recall<Demand>('demand', key);           // WP-105: as for the readiness check
    if (kept) {
      setResult({ state: 'done', data: kept });
      return;
    }
    setResult({ state: 'loading' });
    shared('demand', key, () => fetchDemand(JSON.parse(key))).then(
      (data) => { if (!controller.signal.aborted) setResult({ state: 'done', data }); },
      (e: unknown) => {
        if (controller.signal.aborted) return;
        setResult({ state: 'error', message: e instanceof DemandError ? e.message : DEMAND_FAILED });
      },
    );
    return () => controller.abort();
  }, [key, attempt]);
  return { ...result, retry: () => setAttempt((n) => n + 1) };
}

/**
 * The full official CPV vocabulary (WP-73), loaded after the first render as a chunk of its own, so that no other page carries it. Null while
 * it loads or when it could not be loaded; the callers then use the selection of lib/cpv.ts.
 */
export function useCpvVocabulary(): ReadonlyMap<string, string> | null {
  const [vocab, setVocab] = useState<ReadonlyMap<string, string> | null>(null);
  useEffect(() => {
    let live = true;
    import('@/lib/cpv-full').then((m) => { if (live) setVocab(m.CPV_FULL); }).catch(() => { /* the selection stays */ });
    return () => { live = false; };
  }, []);
  return vocab;
}
