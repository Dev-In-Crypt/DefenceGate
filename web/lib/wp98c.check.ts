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

  // the feed's first page reads FEED_PAGE_ENTRIES (= FEED_MAX) over API pages of FEED_PAGE_SIZE. WP-174 (QA 24 Nov 2026, A-6): the
  // worker no longer keeps those API pages: a kept first page and a live second one overlapped (page 2 repeated 171 entries)
  const api = readFileSync(join(process.cwd(), 'lib', 'api.ts'), 'utf8');
  const size = Number(/export const FEED_PAGE_SIZE = (\d+);/.exec(api)?.[1]);
  assert.match(api, /export const FEED_PAGE_ENTRIES = FEED_MAX;/);
  assert.ok(Number.isInteger(FEED_MAX / size));
  const warm = readFileSync(join(process.cwd(), '..', 'backend', 'dgate', 'ops', 'warm_lists.py'), 'utf8');
  assert.ok(!/^FEED_API_PAGES = /m.test(warm) && !/"changes", snapshot_key\("changes"/.test(warm), 'no stored change pages');

  console.log('wp98c.check: ok');
}

main().catch((e) => { console.error(e); process.exit(1); });
