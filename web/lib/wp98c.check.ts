/**
 * Self-check of WP-98c (production timings after the WP-98b deploy): the feed warmer asks the server's own feeds one after
 * the other and names what did not answer; the worker keeps exactly the API pages the Atom feed's first page reads.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { FEED_MAX } from './analyst';
import { WARM_AGENT, WARM_EVERY_MS, WARM_PATHS, warmOnce } from './feed-warm';

async function main() {
  // one after the other, with its own agent, every unfiltered feed; a failure and a refusal are named, never thrown
  const asked: string[] = [];
  let inFlight = 0;
  const fake = async (url: string, init: RequestInit) => {
    inFlight += 1;
    assert.equal(inFlight, 1, 'never two at once');
    asked.push(url);
    assert.equal((init.headers as Record<string, string>)['user-agent'], WARM_AGENT);
    await new Promise((r) => setTimeout(r, 1));
    inFlight -= 1;
    if (url.endsWith('/digest.atom')) throw new Error('down');
    return new Response('x', { status: url.includes('kind=tenders') ? 502 : 200 });
  };
  const failed = await warmOnce('http://127.0.0.1:3000', fake);
  assert.deepEqual(asked, WARM_PATHS.map((p) => `http://127.0.0.1:3000${p}`));
  assert.deepEqual(failed, ['/calendar.ics?kind=tenders 502', '/digest.atom no answer']);
  assert.ok(WARM_PATHS.includes('/changes.atom') && WARM_PATHS.includes('/funding.ics'));
  assert.ok(WARM_EVERY_MS < 5 * 60_000, 'a round comes before the feed page goes stale (five minutes)');

  // the worker keeps the API pages the feed's first page reads: FEED_PAGE_ENTRIES (= FEED_MAX) over pages of FEED_PAGE_SIZE
  const api = readFileSync(join(process.cwd(), 'lib', 'api.ts'), 'utf8');
  const size = Number(/export const FEED_PAGE_SIZE = (\d+);/.exec(api)?.[1]);
  assert.match(api, /export const FEED_PAGE_ENTRIES = FEED_MAX;/);
  const warm = readFileSync(join(process.cwd(), '..', 'backend', 'dgate', 'ops', 'warm_lists.py'), 'utf8');
  assert.equal(Number(/^FEED_PAGE_SIZE = (\d+)$/m.exec(warm)?.[1]), size, 'warm_lists.FEED_PAGE_SIZE is the feed’s API page');
  const pages = /^FEED_API_PAGES = \(([\d, ]+)\)$/m.exec(warm)?.[1].split(',').map((x) => Number(x.trim())).filter(Boolean);
  assert.deepEqual(pages, Array.from({ length: FEED_MAX / size }, (_, i) => i + 1), 'every API page of the first feed page');

  console.log('wp98c.check: ok');
}

main().catch((e) => { console.error(e); process.exit(1); });
