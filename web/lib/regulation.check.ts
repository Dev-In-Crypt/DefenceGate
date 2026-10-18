/**
 * Self-check of the regulatory tracker feed (WP-36): the Atom document is well-formed enough for a reader, ids are
 * stable, nothing unescaped gets through, and every link of an entry leads somewhere on the site.
 * Not part of the app. Run from web/:  npm run check
 */
import assert from 'node:assert/strict';
import mock from './mock/regulation.json';
import { buildRegulationAtom, linkHref, STATUS_WORD, type RegulationEntry, type RegulationFeed } from './regulation';

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
console.log('regulation.check ok');
