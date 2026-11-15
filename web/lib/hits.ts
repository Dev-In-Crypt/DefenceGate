/**
 * The pure parts of the visit counter (middleware.ts wires them to requests). Import-free, so it runs in the
 * Edge runtime and lib/hits.check.ts can run it on its own.
 *
 * Review of 13 October 2026, H1: one POST per page view drained the API's shared bucket and grew the table
 * with whatever a visitor typed. Now a page view is reduced to a key (path, referrer host, device class and, since
 * WP-169, Cloudflare's country; the API reduces the path to its page and drops the rest unless DGATE_STATS_DETAIL=1),
 * summed in memory, flushed in one batch every FLUSH_MS, and one address counts at most VIEWS_PER_MINUTE a minute.
 * Nothing here holds an address, a user agent or any identifier beyond the limiter's own short-lived counter.
 */

export const FLUSH_MS = 15_000;
export const VIEWS_PER_MINUTE = 120;
/**
 * Distinct keys held between flushes. The API accepts 200 per batch: 100 ordinary keys plus the folded ones
 * (PAGE_KEYS page keys x 2 device classes, referrer `other`) stay under it. Keys beyond the cap are folded, not lost.
 */
export const MAX_KEYS = 100;
/** The API's limit on a path (accounts.Hit.route); a longer one is sent as its page key, so it cannot refuse the batch. */
const MAX_PATH = 200;
const LIMITER_MAX_ENTRIES = 10_000;
/** The API refuses a batch with a count above this; a busier key is clamped, not the whole batch lost. */
const MAX_COUNT = 10_000;

/** Same list as backend/dgate/accounts.py: a page is counted, a record is not, an unknown path is /other. */
const KNOWN_ROUTES = new Set(['', 'funding', 'tenders', 'buyers', 'data', 'market', 'calendar', 'cpv', 'glossary', 'methodology', 'about', 'terms',
  'privacy', 'imprint', 'pricing', 'alerts', 'pack', 'signin', 'register', 'signup', 'reset', 'app',
  'suppliers', 'organisations', 'projects', 'requirements', 'regulation', 'signals', 'networks', 'readiness', 'reports', 'search',
  'changes', 'check', 'digest']);
const DETAIL_ROUTES = new Set(['funding', 'tenders', 'buyers', 'suppliers', 'organisations', 'projects', 'requirements', 'digest']);
/** How many page keys routeKey can return: every known page, the record page of the detail ones, and /other. */
export const PAGE_KEYS = KNOWN_ROUTES.size + DETAIL_ROUTES.size + 1;

export function routeKey(pathname: string): string {
  const parts = pathname.split('?')[0].split('/').filter(Boolean);
  const head = parts[0] ?? '';
  if (!KNOWN_ROUTES.has(head)) return '/other';
  if (DETAIL_ROUTES.has(head) && parts.length >= 2) return `/${head}/[slug]`;
  return head ? `/${head}` : '/';
}

/**
 * The referrer's host, '' for a direct visit and 'internal' for the site itself. Free text on purpose: the API reduces it
 * to its allow-list (else `other`) unless DGATE_STATS_DETAIL=1 (WP-169), and never sees a path or a query.
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
  if (!host || host.length > 80) return '';
  return host === own || host === `www.${own}` ? 'internal' : host;
}

/** First entry of X-Forwarded-For (the one Caddy sets). Anything that is not an address becomes 'unknown'. */
export function clientIp(forwardedFor: string | null): string {
  const first = forwardedFor?.split(',')[0]?.trim() ?? '';
  return /^[0-9A-Fa-f:.]{2,45}$/.test(first) ? first : 'unknown';
}

/** WP-169: Cloudflare's CF-IPCountry (two characters: ISO code, XX or T1), or ''. The API keeps it only with the detail on. */
export function country(value: string | null): string {
  return value && /^[A-Z][A-Z0-9]$/.test(value) ? value : '';
}

/**
 * `route` is the path as asked (WP-169; the API reduces it to its page key unless DGATE_STATS_DETAIL=1), `country` as above.
 */
export interface HitCount { route: string; referrer: string; mobile: boolean; count: number; country: string }

/**
 * Sums page views per (path, referrer, device, country). Bounded: a new key beyond MAX_KEYS is counted on its page key with
 * referrer `other` and no country, a small fixed set.
 */
export class HitBuffer {
  private readonly counts = new Map<string, HitCount>();

  constructor(private readonly maxKeys: number = MAX_KEYS) {}

  get size(): number {
    return this.counts.size;
  }

  add(path: string, referrer: string, mobile: boolean, cc = ''): void {
    let [route, ref, ctry] = [path.length > MAX_PATH ? routeKey(path) : path, referrer, cc];
    if (!this.counts.has(this.key(route, ref, mobile, ctry)) && this.counts.size >= this.maxKeys) {
      [route, ref, ctry] = [routeKey(path), 'other', ''];
    }
    const k = this.key(route, ref, mobile, ctry);
    const hit = this.counts.get(k);
    if (hit) {
      hit.count += 1;
      return;
    }
    // A folded key is (page key, 'other', device, ''), a small fixed set: it may pass the cap.
    this.counts.set(k, { route, referrer: ref, mobile, count: 1, country: ctry });
  }

  /** Everything gathered so far, and the buffer is empty. */
  drain(): HitCount[] {
    const out = [...this.counts.values()].map((h) => ({ ...h, count: Math.min(h.count, MAX_COUNT) }));
    this.counts.clear();
    return out;
  }

  private key(route: string, referrer: string, mobile: boolean, cc: string): string {
    return `${mobile ? 'm' : 'd'}\u0000${route}\u0000${referrer}\u0000${cc}`;
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
