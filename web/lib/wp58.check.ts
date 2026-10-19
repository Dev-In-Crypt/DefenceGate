/**
 * Self-check of WP-58 (accessibility and interaction): the titles of list views and the wording of a failed readiness check.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { buildMetadata, listViewTitle } from './seo';
import { ASSESS_FAILED, AssessError, assess } from './readiness';
import { parseTenderFilters, activeTenderFilterCount } from './filters';

const FULL = 'Defence and dual-use tenders';
// The unfiltered first page keeps the list's own title; a sort is not a filter.
assert.equal(listViewTitle(FULL, 'Tenders', {}), FULL);
assert.equal(listViewTitle(FULL, 'Tenders', { page: 1, filters: 0 }), FULL);
// Paged, by country, searched, filtered otherwise: each view has its own title.
assert.equal(listViewTitle(FULL, 'Tenders', { page: 3 }), 'Tenders, page 3');
assert.equal(listViewTitle(FULL, 'Tenders', { countries: ['DE'], filters: 1 }), 'Tenders in Germany');
assert.equal(listViewTitle(FULL, 'Tenders', { countries: ['DE', 'PL'], filters: 1, page: 2 }), 'Tenders in Germany and Poland, page 2');
assert.equal(listViewTitle(FULL, 'Tenders', { countries: ['DE', 'PL', 'FR'], filters: 1 }), 'Tenders in 3 countries');
assert.equal(listViewTitle(FULL, 'Tenders', { q: 'drone', filters: 1 }), 'Tenders: “drone”');
assert.equal(listViewTitle(FULL, 'Tenders', { filters: 1 }), 'Tenders (filtered)');
assert.equal(listViewTitle(FULL, 'Tenders', { countries: ['DE'], q: 'drone', filters: 3, page: 4 }), 'Tenders in Germany (filtered), page 4: “drone”');

// From the URL, through the page's own filter parser and count, and through the trim rule of buildMetadata (WP-56) unchanged.
const f = parseTenderFilters({ country: 'DE', page: '3' });
const t = listViewTitle(FULL, 'Tenders', { page: f.page, countries: f.country, q: f.q, filters: activeTenderFilterCount(f) });
assert.equal(t, 'Tenders in Germany, page 3');
assert.equal(buildMetadata({ title: t, description: 'x', path: '/tenders' }).title, 'Tenders in Germany, page 3');
// A long search is cut by the same rule; the page number before it survives.
const long = buildMetadata({ title: listViewTitle(FULL, 'Tenders', { page: 2, q: 'very long search words that go on and on', filters: 1 }), description: 'x', path: '/tenders' }).title as string;
assert.ok(long.startsWith('Tenders, page 2: “very') && long.endsWith('…') && long.length <= 46, long);

// A readiness check that gets no answer at all says our sentence, never the browser's "Failed to fetch".
(async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = (() => Promise.reject(new TypeError('Failed to fetch'))) as typeof fetch;
  await assert.rejects(assess({} as never), (e: unknown) => e instanceof AssessError && e.message === ASSESS_FAILED && !/failed to fetch/i.test(e.message));
  // An aborted request stays an abort (the hooks ignore it), not an error to show.
  const ctl = new AbortController(); ctl.abort();
  globalThis.fetch = (() => Promise.reject(new DOMException('aborted', 'AbortError'))) as typeof fetch;
  await assert.rejects(assess({} as never, ctl.signal), (e: unknown) => !(e instanceof AssessError));
  globalThis.fetch = (() => Promise.resolve(new Response('{}', { status: 502 }))) as typeof fetch;
  await assert.rejects(assess({} as never), (e: unknown) => e instanceof AssessError && e.message === ASSESS_FAILED);
  globalThis.fetch = realFetch;
  console.log('wp58 checks passed');
})().catch((e) => { console.error(e); process.exit(1); });
