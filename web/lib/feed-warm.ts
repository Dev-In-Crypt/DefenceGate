/**
 * WP-98c: the feeds a reader subscribes to are built by the server itself, at start and then every few minutes, so that the
 * first reader after a deploy or a quiet hour is served a built page (the unfiltered change feed took 5.1 s cold on
 * production and once answered 502 right after a deploy). The server asks its own routes, one after the other, so what is
 * warmed is exactly what a reader gets: the route's caches (lib/api.ts getChangesForFeed keeps a page fresh five minutes and
 * serves it, while rebuilding, for thirty) and the data cache under them. Pure of Next.js: lib/wp98c.check.ts runs it.
 */

/** The unfiltered feeds and calendars: the addresses subscribed to most (the filtered ones are built on their first read). */
export const WARM_PATHS = ['/changes.atom', '/funding.ics', '/calendar.ics?kind=funding', '/calendar.ics?kind=tenders', '/digest.atom'] as const;
/** Under the feed's five fresh minutes, so a reader always finds a fresh page. */
export const WARM_EVERY_MS = 4 * 60_000;
/** After start: the server is listening by then; a second round catches a slow start. */
export const WARM_FIRST_MS = [5_000, 30_000] as const;
export const WARM_AGENT = 'DefenceGate-warm/1.0 (own server)';

type Fetch = (url: string, init: RequestInit) => Promise<Response>;

/** One round: every path, one after the other (never a burst on the API). The paths that did not answer 200. */
export async function warmOnce(origin: string, fetchFn: Fetch = fetch): Promise<string[]> {
  const failed: string[] = [];
  for (const path of WARM_PATHS) {
    try {
      const r = await fetchFn(`${origin}${path}`, { headers: { 'user-agent': WARM_AGENT }, signal: AbortSignal.timeout(60_000) });
      await r.arrayBuffer();
      if (r.status !== 200) failed.push(`${path} ${r.status}`);
    } catch {
      failed.push(`${path} no answer`);
    }
  }
  return failed;
}

/** Start the rounds (instrumentation.ts). Timers do not keep the process alive. */
export function startFeedWarmer(origin: string): void {
  const round = () => void warmOnce(origin).then((failed) => {
    if (failed.length) console.warn(`feed warm: ${failed.join(', ')}`);
  });
  for (const ms of WARM_FIRST_MS) setTimeout(round, ms).unref();
  setInterval(round, WARM_EVERY_MS).unref();
}
