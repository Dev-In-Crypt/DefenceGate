/**
 * The pure parts of the visit counter (middleware.ts wires them to requests). Import-free, so it runs in the
 * Edge runtime and lib/hits.check.ts can run it on its own.
 *
 * Review of 13 October 2026, H1: one POST per page view drained the API's shared bucket and grew the table
 * with whatever a visitor typed. Now a page view is reduced to a key (page, referrer host, device class),
 * summed in memory, flushed in one batch every FLUSH_MS, and one address counts at most VIEWS_PER_MINUTE a minute.
 * Nothing here holds an address, a user agent or any identifier beyond the limiter's own short-lived counter.
 */

export const FLUSH_MS = 15_000;
export const VIEWS_PER_MINUTE = 120;
/**
 * Distinct keys held between flushes. The API accepts 200 per batch: 150 ordinary keys plus the folded ones
 * (19 page keys x 2 device classes, referrer `other`) stay under it. Keys beyond the cap are folded, not lost.
 */
export const MAX_KEYS = 150;
const LIMITER_MAX_ENTRIES = 10_000;
/** The API refuses a batch with a count above this; a busier key is clamped, not the whole batch lost. */
const MAX_COUNT = 10_000;

/** Same list as backend/dgate/accounts.py: a page is counted, a record is not, an unknown path is /other. */
const KNOWN_ROUTES = new Set(['', 'funding', 'tenders', 'buyers', 'data', 'market', 'calendar', 'cpv', 'glossary', 'methodology', 'about', 'terms',
  'privacy', 'imprint', 'pricing', 'alerts', 'pack', 'signin', 'register', 'signup', 'reset', 'app']);
const DETAIL_ROUTES = new Set(['funding', 'tenders', 'buyers']);

export function routeKey(pathname: string): string {
  const parts = pathname.split('?')[0].split('/').filter(Boolean);
  const head = parts[0] ?? '';
  if (!KNOWN_ROUTES.has(head)) return '/other';
  if (DETAIL_ROUTES.has(head) && parts.length >= 2) return `/${head}/[slug]`;
  return head ? `/${head}` : '/';
}

/**
 * The referrer's host, or '' for a direct visit and for the site itself. Free text on purpose: the API keeps it
 * only when it is on its allow-list and stores everything else as `other`.
 */
export function referrerHost(value: string | null, ownHost: string): string {
  if (!value) return '';
  let host: string;
  try {
    host = new URL(value).hostname.toLowerCase();
  } catch {
    return '';
  }
  const own = ownHost.toLowerCase();
  if (!host || host.length > 80 || host === own || host === `www.${own}`) return '';
  return host;
}

/** First entry of X-Forwarded-For (the one Caddy sets). Anything that is not an address becomes 'unknown'. */
export function clientIp(forwardedFor: string | null): string {
  const first = forwardedFor?.split(',')[0]?.trim() ?? '';
  return /^[0-9A-Fa-f:.]{2,45}$/.test(first) ? first : 'unknown';
}

export interface HitCount { route: string; referrer: string; mobile: boolean; count: number }

/** Sums page views per (route, referrer, device). Bounded: a new key beyond MAX_KEYS counts as referrer `other`. */
export class HitBuffer {
  private readonly counts = new Map<string, HitCount>();

  constructor(private readonly maxKeys: number = MAX_KEYS) {}

  get size(): number {
    return this.counts.size;
  }

  add(route: string, referrer: string, mobile: boolean): void {
    let ref = referrer;
    if (!this.counts.has(this.key(route, ref, mobile)) && this.counts.size >= this.maxKeys) ref = 'other';
    const k = this.key(route, ref, mobile);
    const hit = this.counts.get(k);
    if (hit) {
      hit.count += 1;
      return;
    }
    // `route` is already a page key, so (route, 'other', device) is a small fixed set: it may pass the cap.
    this.counts.set(k, { route, referrer: ref, mobile, count: 1 });
  }

  /** Everything gathered so far, and the buffer is empty. */
  drain(): HitCount[] {
    const out = [...this.counts.values()].map((h) => ({ ...h, count: Math.min(h.count, MAX_COUNT) }));
    this.counts.clear();
    return out;
  }

  private key(route: string, referrer: string, mobile: boolean): string {
    return `${mobile ? 'm' : 'd'}\u0000${route}\u0000${referrer}`;
  }
}

/** At most `limit` counted page views per address per window (fixed window). Beyond it nothing is counted. */
export class IpLimiter {
  private readonly windows = new Map<string, { start: number; n: number }>();

  constructor(
    private readonly limit: number = VIEWS_PER_MINUTE,
    private readonly windowMs: number = 60_000,
    private readonly maxEntries: number = LIMITER_MAX_ENTRIES,
  ) {}

  allow(ip: string, now: number): boolean {
    const w = this.windows.get(ip);
    if (!w || now - w.start >= this.windowMs) {
      if (!w && this.windows.size >= this.maxEntries) this.purge(now);
      this.windows.set(ip, { start: now, n: 1 });
      return true;
    }
    if (w.n >= this.limit) return false;
    w.n += 1;
    return true;
  }

  private purge(now: number): void {
    for (const [ip, w] of this.windows) if (now - w.start >= this.windowMs) this.windows.delete(ip);
    if (this.windows.size >= this.maxEntries) this.windows.clear();   // a flood of addresses: start over, stay bounded
  }
}
