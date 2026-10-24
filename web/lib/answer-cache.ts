/**
 * WP-105 (persona round of 24 October 2026, p02: "Too many requests" in all three sections when the report was opened right after the
 * results page): the answers of the readiness check and of the demand map, kept in this browser's tab (sessionStorage) for a few minutes
 * under their request, so that the results page and the report ask the API once for the same profile. The request is the profile's own
 * answers and codes, which this browser already holds (localStorage); nothing goes to the server. Lost when the tab closes.
 */
export const ANSWER_SECONDS = 10 * 60;
const PREFIX = 'dg-answer:';

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function store(): Store | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;                       // storage refused (privacy mode): every request goes to the API, as before
  }
}

/** The answer kept for this request, if it is younger than ANSWER_SECONDS. */
export function recall<T>(kind: string, key: string, now = Date.now(), s: Store | null = store()): T | null {
  if (!s || !key) return null;
  try {
    const raw = s.getItem(PREFIX + kind + ':' + key);
    if (!raw) return null;
    const { at, data } = JSON.parse(raw) as { at: number; data: T };
    if (typeof at !== 'number' || now - at > ANSWER_SECONDS * 1000) {
      s.removeItem(PREFIX + kind + ':' + key);
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

/** WP-105: the longest Retry-After the readiness calls wait out on their own, once, before they show "Too many requests". */
export const PATIENCE_SECONDS = 20;

/**
 * A POST of the readiness check or the demand map: a 429 whose Retry-After is at most PATIENCE_SECONDS is waited out and asked once more,
 * so a visitor who opens the report seconds after other pages sees the report, not "Too many requests". The wait ends with `signal`.
 */
export async function fetchPatiently(input: string, init: RequestInit,
  wait = (ms: number) => new Promise<void>((r) => { setTimeout(r, ms); })): Promise<Response> {
  const first = await fetch(input, init);
  if (first.status !== 429) return first;
  const after = Number(first.headers.get('retry-after') ?? '');
  if (!Number.isFinite(after) || after < 0 || after > PATIENCE_SECONDS) return first;
  await wait(Math.max(1, after) * 1000);
  if (init.signal?.aborted) return first;
  return fetch(input, init);
}

/** Keep the answer to this request; one per kind (the newest), so the tab holds at most a few. */
export function remember(kind: string, key: string, data: unknown, now = Date.now(), s: Store | null = store()): void {
  if (!s || !key) return;
  try {
    const last = s.getItem(PREFIX + kind);
    if (last && last !== key) s.removeItem(PREFIX + kind + ':' + last);
    s.setItem(PREFIX + kind + ':' + key, JSON.stringify({ at: now, data }));
    s.setItem(PREFIX + kind, key);
  } catch {
    /* full or refused: not kept */
  }
}
