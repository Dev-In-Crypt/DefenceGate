/**
 * Self-check of the regulatory tracker feed (WP-36): the Atom document is well-formed enough for a reader, ids are
 * stable, nothing unescaped gets through, and every link of an entry leads somewhere on the site.
 * Not part of the app. Run from web/:  npm run check
 */
import assert from 'node:assert/strict';
import mock from './mock/regulation.json';
import { buildRegulationAtom, citation, entryUrl, linkHref, newestFirst, STATUS_WORD, type RegulationEntry, type RegulationFeed } from './regulation';

const feed = mock as unknown as RegulationFeed;
assert.ok(feed.entries.length > 5, 'the mock holds the seed');
for (const e of feed.entries) {
  assert.ok(e.source.url.startsWith('http'), `${e.code}: source url`);
  assert.ok(e.source.quote.length >= 25, `${e.code}: a verbatim sentence`);
  assert.match(e.checkedOn, /^\d{4}-\d{2}-\d{2}$/, `${e.code}: checked day`);
  assert.ok(e.status in STATUS_WORD, `${e.code}: status`);
  for (const l of e.links) assert.match(linkHref(l), /^\//, `${e.code}: link ${l.code}`);
}
assert.equal(new Set(feed.entries.map((e) => e.code)).size, feed.entries.length, 'codes are unique');

const nasty: RegulationFeed = {
  entries: [{ ...(feed.entries[0] as RegulationEntry), code: 'x', title: 'A & B <c> "d"\u0007', whatChanged: 'It “changed” & more.' }],
  lastChecked: '2026-10-18', notice: '',
};
const xml = buildRegulationAtom(nasty, { origin: 'https://defencegatehub.com', generatedAt: '2026-10-18T00:00:00Z' });
assert.ok(xml.startsWith('<?xml version="1.0" encoding="utf-8"?>'));
assert.ok(xml.includes('A &amp; B &lt;c&gt; &quot;d&quot; ('), 'title escaped, control character dropped');
assert.ok(!xml.includes('\u0007'));
assert.equal((xml.match(/<entry>/g) ?? []).length, 1);
assert.ok(xml.includes('<id>tag:defencegatehub.com,2026:regulation:x</id>'), 'stable id');
assert.ok(xml.includes('<updated>2026-10-18T00:00:00Z</updated>'));
const again = buildRegulationAtom(nasty, { origin: 'https://defencegatehub.com', generatedAt: '2030-01-01T00:00:00Z' });
assert.equal(xml, again, 'the same entries give the same document whatever the time of the request');
// U12: newest event first, whatever the order of the seed; ties by code; the input is not changed.
const e = (code: string, eventDate: string, status: RegulationEntry['status'] = 'adopted'): RegulationEntry =>
  ({ ...(feed.entries[0] as RegulationEntry), code, eventDate, status, title: `Title ${code}` });
const shuffled = [e('b', '2025-12-30'), e('u', '2026-10-09', 'unconfirmed'), e('c', '2026-06-15'), e('a', '2026-06-15')];
assert.deepEqual(newestFirst(shuffled).map((x) => x.code), ['u', 'a', 'c', 'b']);
assert.deepEqual(shuffled.map((x) => x.code), ['b', 'u', 'c', 'a'], 'the input order is kept');
// The Atom feed follows the same order.
const atomOrder = buildRegulationAtom({ entries: shuffled, lastChecked: null, notice: '' }, { origin: 'https://defencegatehub.com', generatedAt: '2026-10-18T00:00:00Z' });
assert.ok(atomOrder.indexOf('regulation:u<') < atomOrder.indexOf('regulation:b<'), 'newest entry first in the feed');
// A permalink and a line to cite: the title, the dates, the address of the entry and the primary source.
assert.equal(entryUrl('https://defencegatehub.com', 'edip-in-force'), 'https://defencegatehub.com/regulation#edip-in-force');
const cite = citation(e('x1', '2026-06-15'), 'https://defencegatehub.com');
assert.ok(cite.includes('Title x1') && cite.includes('event of 2026-06-15') && cite.includes('https://defencegatehub.com/regulation#x1'), cite);
assert.ok(cite.includes((feed.entries[0] as RegulationEntry).source.url), 'the primary source is in the line');
assert.ok(cite.includes('source last checked'), 'and the day we read it');
console.log('regulation.check ok');
