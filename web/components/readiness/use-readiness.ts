'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { clearProfile, emptyProfile, loadProfile, saveProfile, toRequest, type Profile } from '@/lib/profile';
import { assess } from '@/lib/readiness';
import type { Assessment } from '@/lib/readiness-types';

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

/** Ask the API for the verdict of the profile whenever its answers change. Nothing is kept. */
export function useAssessment(profile: Profile | null): AssessState & { retry: () => void } {
  const [result, setResult] = useState<AssessState>({ state: 'idle' });
  const [attempt, setAttempt] = useState(0);
  const seq = useRef(0);
  const request = profile ? toRequest(profile) : null;
  const key = request ? JSON.stringify(request) : '';
  useEffect(() => {
    if (!key) {
      setResult({ state: 'idle' });
      return;
    }
    const controller = new AbortController();
    const mine = ++seq.current;
    setResult((r) => (r.state === 'done' ? r : { state: 'loading' }));
    assess(JSON.parse(key), controller.signal).then(
      (data) => { if (mine === seq.current) setResult({ state: 'done', data }); },
      (e: unknown) => {
        if (controller.signal.aborted || mine !== seq.current) return;
        setResult({ state: 'error', message: e instanceof Error ? e.message : 'The check could not be computed.' });
      },
    );
    return () => controller.abort();
  }, [key, attempt]);
  return { ...result, retry: () => setAttempt((n) => n + 1) };
}
