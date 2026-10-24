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

/**
 * WP-105: the longest the readiness calls wait out "Too many requests" on their own before they show it. WP-112 (p02, round 4: still
 * "Too many requests" in two sections): the API's bucket refills at two tokens a second, so a refused request is told to wait 1-3 s,
 * and the one retry lost again when other requests from the same address (a shared office network) took those tokens first. Now it
 * asks again after each Retry-After until PATIENCE_SECONDS have been waited in all.
 */
export const PATIENCE_SECONDS = 30;

/**
 * A POST of the readiness check or the demand map: a 429 whose Retry-After fits in what is left of PATIENCE_SECONDS is waited out and
 * asked again, as often as that holds. The wait ends with `signal`.
 */
export async function fetchPatiently(input: string, init: RequestInit,
  wait = (ms: number) => new Promise<void>((r) => { setTimeout(r, ms); }),
  get: typeof fetch = (i, o) => fetch(i, o), clock: () => number = Date.now): Promise<Response> {
  // the patience is counted in time since the first request, the requests' own time included (WP-112, p03: a report that had not
  // finished after 60 s), so a slow API and a busy one together never keep a section waiting past PATIENCE_SECONDS and one request
  const start = clock();
  let res = await get(input, init);
  while (res.status === 429) {
    const after = Number(res.headers.get('retry-after') ?? '');
    if (!Number.isFinite(after) || after < 0) return res;
    const seconds = Math.max(1, after);
    if (clock() - start + seconds * 1000 > PATIENCE_SECONDS * 1000) return res;
    await wait(seconds * 1000);
    if (init.signal?.aborted) return res;
    res = await get(input, init);
  }
  return res;
}

/**
 * WP-112 (p02): one request in flight per kind and key, shared by every page of the tab. The results page asks for the demand map,
 * which takes seconds; a visitor who clicked "My supplier report" before it answered aborted it and the report asked again (two charges
 * on the API's rate limit, the second often refused). The request is no longer tied to the page that started it: it runs to its end,
 * is kept (`remember`), and the next page waits for the same answer. A failed request is forgotten, so a retry asks again.
 */
const inFlight = new Map<string, Promise<unknown>>();

export function shared<T>(kind: string, key: string, run: () => Promise<T>, s: Store | null = store()): Promise<T> {
  const id = kind + ':' + key;
  const going = inFlight.get(id) as Promise<T> | undefined;
  if (going) return going;
  const p = run().then(
    (data) => { inFlight.delete(id); remember(kind, key, data, Date.now(), s); return data; },
    (e: unknown) => { inFlight.delete(id); throw e; },
  );
  inFlight.set(id, p);
  return p;
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
