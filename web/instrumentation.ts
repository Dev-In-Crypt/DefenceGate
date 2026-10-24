/**
 * Runs once when the server starts (Next.js instrumentation). WP-98c: the feed warmer (lib/feed-warm.ts), on a server that reads
 * the API (DG_API_URL) only: a demo build or a test run has nothing to warm. DG_WARM_FEEDS=0 turns it off.
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== 'nodejs' || !process.env.DG_API_URL || process.env.DG_WARM_FEEDS === '0') return;
  const { startFeedWarmer } = await import('./lib/feed-warm');
  startFeedWarmer(`http://127.0.0.1:${process.env.PORT ?? 3000}`);
}
