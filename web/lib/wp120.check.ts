/**
 * Self-check of WP-120 (speed and caching, round-6 system audit of 25 October 2026): a feed's own Last-Modified is "not
 * modified" (changes.atom answered 200 to it), a kept feed answers 304 and repeats without a build, the companies list says
 * "too many requests" as such, the buyer page shows the first open and planned tenders with a link to all. Not part of the
 * app and not imported by it. Run from web/:  npm run check
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { notModified, withCachedEtag } from './etag';

const at = (headers: Record<string, string>) => new Request('https://x.test/changes.atom?country=DE', { headers });

// ---- 6. If-Modified-Since against a time with milliseconds, at the header's whole second ----
const changed = new Date('2026-10-25T06:44:06.789Z');
assert.ok(notModified(at({ 'if-modified-since': changed.toUTCString() }), '"t"', changed), 'its own Last-Modified is not modified');
assert.ok(notModified(at({ 'if-modified-since': 'Sun, 25 Oct 2026 07:00:00 GMT' }), '"t"', changed));
assert.ok(!notModified(at({ 'if-modified-since': 'Sun, 25 Oct 2026 06:44:05 GMT' }), '"t"', changed), 'a second before is modified');
assert.ok(!notModified(at({ 'if-modified-since': 'not a date' }), '"t"', changed));
assert.ok(!notModified(at({}), '"t"', changed));
// If-None-Match wins when both are sent (RFC 9110 13.2.2), with weak tags and lists
assert.ok(notModified(at({ 'if-none-match': 'W/"t", "u"', 'if-modified-since': 'Thu, 01 Jan 1970 00:00:00 GMT' }), '"t"', changed));
assert.ok(!notModified(at({ 'if-none-match': '"u"', 'if-modified-since': changed.toUTCString() }), '"t"', changed));
assert.ok(!notModified(at({ 'if-modified-since': changed.toUTCString() }), '"t"'), 'no date: only the tag can match');
for (const route of ['changes.atom', 'digest.atom', 'regulation.atom']) {
  assert.match(readFileSync(`app/(public)/${route}/route.ts`, 'utf8'), /notModified\(request, etag, lastModified\)/, route);
}

// ---- 5. a kept answer: one build, 304 and 200 from it; an error is never kept ----
async function kept(): Promise<void> {
  let builds = 0;
  const build = async () => { builds += 1; return new Response('BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n', { headers: { 'cache-control': 'public, max-age=3600', 'content-type': 'text/calendar' } }); };
  const url = 'https://x.test/calendar.ics?kind=tenders';
  const first = await withCachedEtag(new Request(url), 3_600_000, build);
  const tag = first.headers.get('etag')!;
  assert.equal(first.status, 200);
  assert.equal(await first.text(), 'BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n');
  const again = await withCachedEtag(new Request(url, { headers: { 'if-none-match': tag } }), 3_600_000, build);
  assert.equal(again.status, 304);
  assert.equal(again.headers.get('cache-control'), 'public, max-age=3600');
  const twice = await withCachedEtag(new Request(url), 3_600_000, build);
  assert.equal(await twice.text(), 'BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n', 'a kept body can be sent again');
  assert.equal(builds, 1, 'built once');
  await withCachedEtag(new Request(`${url}&country=DE`), 3_600_000, build);
  assert.equal(builds, 2, 'another address is another answer');
  let failures = 0;
  const failing = async () => { failures += 1; return new Response('down', { status: 502 }); };
  assert.equal((await withCachedEtag(new Request('https://x.test/funding.atom'), 3_600_000, failing)).status, 502);
  assert.equal((await withCachedEtag(new Request('https://x.test/funding.atom'), 3_600_000, failing)).status, 502);
  assert.equal(failures, 2, 'an error is not kept');
}
for (const route of ['calendar.ics', 'funding.atom']) {
  assert.match(readFileSync(`app/(public)/${route}/route.ts`, 'utf8'), /withCachedEtag\(request, /, route);
}

// ---- 9. the companies list on a 429 ----
const companies = readFileSync('app/(public)/suppliers/page.tsx', 'utf8');
assert.match(companies, /e\.status === 429/);
assert.match(companies, /<ErrorState title="Too many requests from your network just now"/);

// ---- 2. the buyer page: the first open and planned tenders, and all of them on ?all=1 ----
const buyer = readFileSync('app/(public)/buyers/[slug]/page.tsx', 'utf8');
assert.match(buyer, /const OPEN_SHOWN = 20;/);
assert.match(buyer, /const PLANNED_SHOWN = 10;/);
assert.match(buyer, /pageSize: openSize/);
assert.match(buyer, /pageSize: plannedSize/);
assert.match(buyer, /q\.set\('all', '1'\)/);

kept().then(() => console.log('wp120 checks passed')).catch((e) => { console.error(e); process.exit(1); });
