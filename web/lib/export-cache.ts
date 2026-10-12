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
/** The widest export (`status=all`) holds at most this many rows; every other export keeps its own cap. */
export const EXPORT_ALL_CAP = 1000;
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

/**
 * The same result is built once at a time: concurrent identical requests share the running build, and a build
 * that finished is served from the cache. `run` is only called when neither exists and the gate lets it in;
 * otherwise the answer is `busy`. A failed build is never cached.
 */
export class ExportRunner<V> {
  private readonly pending = new Map<string, Promise<V>>();

  constructor(private readonly cache: TtlCache<V>, private readonly gate: Gate) {}

  async get(key: string, run: () => Promise<V>): Promise<{ value: V } | { busy: true }> {
    const hit = this.cache.get(key);
    if (hit !== undefined) return { value: hit };
    const shared = this.pending.get(key);
    if (shared) return { value: await shared };
    if (!this.gate.enter()) return { busy: true };
    const job = run()
      .then((value) => { this.cache.set(key, value); return value; })
      .finally(() => { this.gate.leave(); this.pending.delete(key); });
    this.pending.set(key, job);
    return { value: await job };
  }
}
