/**
 * The pieces that keep the CSV exports cheap and hard to abuse (QA 12 October 2026: 6.8 s for a default export,
 * 26.6 s for `status=all&scope=all`, and nothing stopped a loop of them): a small in-process cache, a cap on the
 * widest exports and a limit on how many uncached ones run at once. Per server process, on purpose: no new
 * infrastructure, and a restart empties it. Pure and import-free so lib/export.check.ts can run it on its own.
 */

/** Entries live this long, at most this many are kept (the oldest goes first), the key is the normalised query. */
export const EXPORT_CACHE_TTL_MS = 10 * 60 * 1000;
export const EXPORT_CACHE_MAX = 30;
/** More uncached exports than this running at once are refused with 429. */
export const EXPORT_MAX_RUNNING = 6;
/** ... and more than this for one client: six slots held by one address refused everyone else (audit X-4). */
export const EXPORT_PER_CLIENT = 2;
/** Rows a CSV holds at most (the pages say so; lib/export.ts has the same number as EXPORT_CAP). */
export const EXPORT_ROW_CAP = 2000;
/** The widest export (`status=all`) holds at most this many rows; every other export keeps its own cap. */
export const EXPORT_ALL_CAP = 1000;
/** A failed build is remembered this long, so a broken query is not re-run by every click and reload (and no longer). */
export const EXPORT_FAILURE_TTL_MS = 30 * 1000;
/** The page sizes of a cursor export: the first request, and the floor it degrades to. */
export const EXPORT_PAGE_START = 1000;
export const EXPORT_PAGE_MIN = 125;
export const EXPORT_RETRY_BACKOFF_MS = 1000;
/** Seconds a refused client is told to wait. */
export const EXPORT_RETRY_AFTER_SECONDS = 15;

export class TtlCache<V> {
  private readonly entries = new Map<string, { at: number; value: V }>();

  constructor(private readonly ttlMs: number, private readonly max: number, private readonly clock: () => number = Date.now) {}

  get(key: string): V | undefined {
    const hit = this.entries.get(key);
    if (!hit) return undefined;
    if (this.clock() - hit.at >= this.ttlMs) {
      this.entries.delete(key);
      return undefined;
    }
    return hit.value;
  }

  set(key: string, value: V): void {
    this.entries.delete(key);                                 // a rewritten key becomes the newest
    this.entries.set(key, { at: this.clock(), value });
    while (this.entries.size > this.max) {
      const oldest = this.entries.keys().next().value as string;
      this.entries.delete(oldest);
    }
  }

  get size(): number {
    return this.entries.size;
  }
}

/** A counter with a ceiling: `enter()` is false when `max` are already inside. */
export class Gate {
  private inside = 0;

  constructor(private readonly max: number) {}

  enter(): boolean {
    if (this.inside >= this.max) return false;
    this.inside += 1;
    return true;
  }

  leave(): void {
    this.inside = Math.max(0, this.inside - 1);
  }

  get running(): number {
    return this.inside;
  }
}

/** Rows one export may hold: `status=all` is capped at EXPORT_ALL_CAP, anything else at `cap`. */
export function exportCap(status: string | undefined, cap: number): number {
  return status === 'all' ? Math.min(cap, EXPORT_ALL_CAP) : cap;
}

/** Every status and every scope with nothing to narrow them is the whole archive: refused before any database time is spent. */
export function tooBroad(f: {
  status?: string; scope?: string; q?: string; country?: unknown[]; cpv?: unknown[]; buyer?: unknown;
  deadlineFrom?: string; deadlineTo?: string; valueMin?: number; valueMax?: number;
}): boolean {
  const narrowed = Boolean(f.q || f.country?.length || f.cpv?.length || f.buyer || f.deadlineFrom || f.deadlineTo
    || f.valueMin !== undefined || f.valueMax !== undefined);
  return f.status === 'all' && f.scope === 'all' && !narrowed;
}

/**
 * The list's order for a file read by id. With a `sort` (the list's own parameter) that order is used: `deadline-asc`,
 * `deadline-desc`, `published-desc`; none last. With none, the soonest deadline first (the latest first for closed).
 * The file used to ignore `sort` (UX walk-through 16 October 2026): 1,000 rows came out in the order of the id.
 */
export function listOrder<T extends { deadline: string | null; publishedAt?: string | null }>(
  items: T[], status: string | undefined, sort?: string,
): T[] {
  const by = sort ?? (status === 'closed' ? 'deadline-desc' : 'deadline-asc');
  const sign = by === 'deadline-asc' ? 1 : -1;
  const at = (t: T) => Date.parse((by === 'published-desc' ? t.publishedAt : t.deadline) ?? '');
  return [...items].sort((a, b) => {
    const x = at(a), y = at(b);
    if (Number.isNaN(x) || Number.isNaN(y)) return Number.isNaN(x) === Number.isNaN(y) ? 0 : Number.isNaN(x) ? 1 : -1;
    return sign * (x - y);
  });
}

/**
 * Reads a result by cursor, `size` rows at a time (the API's export endpoint: a cheap keyed scan, no total), up to
 * `cap` rows. A page that fails with something `retryable` is asked again once, after a pause, at half the size
 * (never below EXPORT_PAGE_MIN), and the smaller size is kept for the pages after it: a slow query is answered
 * with a smaller page, not with an error. `more` is true when the cursor still had rows when `cap` was reached.
 * A second failure on the same page is thrown.
 */
export async function collectByCursor<T>(
  fetchPage: (cursor: string | null, size: number) => Promise<{ items: T[]; nextCursor: string | null }>,
  cap: number,
  opts: { retryable: (err: unknown) => boolean; sleep?: (ms: number) => Promise<void>; start?: number; backoffMs?: number },
): Promise<{ items: T[]; more: boolean }> {
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  let size = Math.min(opts.start ?? EXPORT_PAGE_START, cap);
  let cursor: string | null = null;
  const items: T[] = [];
  for (;;) {
    const want = Math.min(size, cap - items.length);
    let page: { items: T[]; nextCursor: string | null };
    try {
      page = await fetchPage(cursor, want);
    } catch (err) {
      if (!opts.retryable(err)) throw err;
      size = Math.max(EXPORT_PAGE_MIN, Math.floor(size / 2));
      await sleep(opts.backoffMs ?? EXPORT_RETRY_BACKOFF_MS);
      page = await fetchPage(cursor, Math.min(size, cap - items.length));
    }
    items.push(...page.items);
    cursor = page.nextCursor;
    if (cursor === null) return { items, more: false };
    if (items.length >= cap) return { items, more: true };
  }
}

/**
 * The same result is built once at a time: concurrent identical requests share the running build, and a build
 * that finished is served from the cache. `run` is only called when neither exists and the gate lets it in;
 * otherwise the answer is `busy`. A failed build is remembered for EXPORT_FAILURE_TTL_MS only and rethrown.
 */
export class ExportRunner<V> {
  private readonly pending = new Map<string, Promise<V>>();
  private readonly byClient = new Map<string, number>();

  /** `perClient`: the most uncached builds one client may have running (the gate is the total). */
  constructor(
    private readonly cache: TtlCache<V>, private readonly gate: Gate, private readonly perClient = Number.POSITIVE_INFINITY,
    private readonly failures: TtlCache<unknown> = new TtlCache(EXPORT_FAILURE_TTL_MS, EXPORT_CACHE_MAX),
  ) {}

  async get(key: string, run: () => Promise<V>, client = 'unknown'): Promise<{ value: V } | { busy: true }> {
    const hit = this.cache.get(key);
    if (hit !== undefined) return { value: hit };
    const shared = this.pending.get(key);
    if (shared) return { value: await shared };
    if (this.failures.get(key) !== undefined) throw this.failures.get(key);
    if ((this.byClient.get(client) ?? 0) >= this.perClient || !this.gate.enter()) return { busy: true };
    this.byClient.set(client, (this.byClient.get(client) ?? 0) + 1);
    const job = run()
      .then((value) => { this.cache.set(key, value); return value; })
      .catch((err: unknown) => { this.failures.set(key, err ?? new Error('export failed')); throw err; })
      .finally(() => {
        this.gate.leave();
        this.pending.delete(key);
        const left = (this.byClient.get(client) ?? 1) - 1;
        if (left > 0) this.byClient.set(client, left); else this.byClient.delete(client);
      });
    this.pending.set(key, job);
    return { value: await job };
  }
}
