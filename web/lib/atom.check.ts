/**
 * Self-check of the "what changed" feed (WP-10): the Atom document is well-formed and carries what RFC 4287
 * requires, its ids are stable, nothing unescaped or invalid gets through, and the filters round-trip.
 * Not part of the app and not imported by it. Run from web/:  npm run check
 * (or: npx tsc lib/atom.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/atom.check.js)
 */
import assert from 'node:assert/strict';
import { buildAtom, entryTitle, etagOf, rfc3339, tagId, xmlText } from './atom';
import { parseChangeFilters, toChangeQuery } from './filters';
import { queryChanges } from './mock/tenders';
import type { Change, Tender } from './types';

const tender = (over: Partial<Tender>): Tender => ({
  id: '7', slug: '7-armoured-vehicles', noticeId: 'N-7', title: 'Armoured vehicles', titleLanguage: 'en', originalTitle: null,
  originalLanguage: null, buyerId: '3', buyerSlug: '3-ministry', buyerName: 'Ministry of Defence', country: 'FR', cpv: '35400000',
  cpvCodes: ['35400000'], procedure: null, legalBasis: null, scope: 'core', deadline: null, publishedAt: null, estimatedValue: null,
  status: 'open', statusNative: 'open', amended: false, versionCount: 1, securityClearance: false, subcontracting: false, sameNotice: [],
  source: { sourceId: 'ted', sourceName: 'TED', url: null, retrievedAt: '2026-10-14T06:00:00Z', licence: '', attribution: '' },
  ...over,
});

const changes: Change[] = [
  { id: '7-20261014', kind: 'amended', day: '2026-10-14', detectedAt: '2026-10-14T06:20:11.512Z',
    changes: [{ field: 'deadline_at', label: 'Deadline', before: '12 Nov 2026', after: '26 Nov 2026' }], tender: tender({}) },
  { id: '9-20261013', kind: 'new', day: '2026-10-13', detectedAt: '2026-10-13T06:05:00Z', changes: [],
    tender: tender({ id: '9', slug: '9-a-b', title: 'Supply of <boots> & "gloves"\u0007', buyerName: 'A & B', country: null }) },
];

const options = {
  origin: 'https://defencegatehub.com', selfPath: '/changes.atom', pagePath: '/changes', title: 'DefenceGate: what changed',
  subtitle: 'The last 14 days.', generatedAt: '2026-10-15T00:00:00Z',
};

// ---- a small XML reader: well-formedness (tags nest, attributes quoted, entities known) ----
interface Node { name: string; attrs: Record<string, string>; children: Node[]; text: string }
function parseXml(xml: string): Node {
  const root: Node = { name: '#root', attrs: {}, children: [], text: '' };
  const stack: Node[] = [root];
  const re = /<\?xml[^>]*\?>|<!--[\s\S]*?-->|<\/([A-Za-z][\w:.-]*)\s*>|<([A-Za-z][\w:.-]*)((?:\s+[\w:.-]+="[^"<]*")*)\s*(\/?)>|([^<]+)/g;
  let m: RegExpExecArray | null;
  let consumed = 0;
  while ((m = re.exec(xml)) !== null) {
    assert.equal(m.index, consumed, `unparsed text at ${consumed}: ${xml.slice(consumed, consumed + 30)}`);
    consumed = re.lastIndex;
    const top = stack[stack.length - 1];
    if (m[1] !== undefined) {
      assert.equal(top.name, m[1], `closing </${m[1]}> but <${top.name}> is open`);
      stack.pop();
    } else if (m[2] !== undefined) {
      const attrs: Record<string, string> = {};
      for (const a of m[3].matchAll(/([\w:.-]+)="([^"]*)"/g)) attrs[a[1]] = a[2];
      const node: Node = { name: m[2], attrs, children: [], text: '' };
      top.children.push(node);
      if (m[4] !== '/') stack.push(node);
    } else if (m[5] !== undefined) {
      assert.ok(!/[<>]/.test(m[5]), 'raw angle bracket in text');
      // Every ampersand starts one of the five predefined entities.
      assert.ok(!/&(?!(amp|lt|gt|quot|apos);)/.test(m[5]), `bare ampersand in: ${m[5]}`);
      assert.ok(!/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(m[5]), 'control character in text');
      top.text += m[5];
    }
  }
  assert.equal(consumed, xml.length, 'trailing unparsed content');
  assert.equal(stack.length, 1, 'unclosed element');
  assert.equal(root.children.length, 1, 'exactly one root element');
  return root.children[0];
}
const kids = (n: Node, name: string) => n.children.filter((c) => c.name === name);
const RFC3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

const xml = buildAtom(changes, options);
assert.ok(xml.startsWith('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"'), 'declaration and namespace');
const feed = parseXml(xml);
assert.equal(feed.name, 'feed');
assert.equal(feed.attrs.xmlns, 'http://www.w3.org/2005/Atom');

// RFC 4287 4.1.1: the feed's required elements, once each, and a self link.
for (const name of ['id', 'title', 'updated']) assert.equal(kids(feed, name).length, 1, `feed ${name}`);
assert.match(kids(feed, 'updated')[0].text, RFC3339);
assert.equal(kids(feed, 'updated')[0].text, '2026-10-14T06:20:11Z', 'feed updated is the newest entry');
const self = kids(feed, 'link').filter((l) => l.attrs.rel === 'self');
assert.equal(self.length, 1);
assert.equal(self[0].attrs.href, 'https://defencegatehub.com/changes.atom');
assert.equal(self[0].attrs.type, 'application/atom+xml');
assert.equal(kids(feed, 'author').length, 1, 'a feed-level author, as the entries carry none');
assert.equal(kids(kids(feed, 'author')[0], 'name')[0].text, 'DefenceGate');

// Entries: id, title, updated, an alternate link; ids unique and stable tag URIs.
const entries = kids(feed, 'entry');
assert.equal(entries.length, 2);
const ids = entries.map((e) => kids(e, 'id')[0].text);
assert.equal(new Set(ids).size, 2);
assert.deepEqual(ids, ['tag:defencegatehub.com,2026:change:7-20261014', 'tag:defencegatehub.com,2026:change:9-20261013']);
for (const e of entries) {
  for (const name of ['id', 'title', 'updated']) assert.equal(kids(e, name).length, 1, `entry ${name}`);
  assert.match(kids(e, 'updated')[0].text, RFC3339);
  const alt = kids(e, 'link').filter((l) => l.attrs.rel === 'alternate');
  assert.equal(alt.length, 1);
  assert.match(alt[0].attrs.href, /^https:\/\/defencegatehub\.com\/tenders\/\d+-/);
  assert.ok(kids(e, 'summary')[0].text.length > 0);
}
assert.equal(kids(entries[0], 'title')[0].text, 'Amended: Armoured vehicles');
assert.match(kids(entries[0], 'summary')[0].text, /Deadline: 12 Nov 2026 to 26 Nov 2026/);
assert.equal(kids(entries[1], 'category')[0].attrs.term, 'new');
// Escaped and cleaned: markup characters in a title stay text, a control character is gone.
assert.equal(kids(entries[1], 'title')[0].text, 'New: Supply of &lt;boots&gt; &amp; &quot;gloves&quot;');

// Stability: the same change on a later run has the same id and the same validator; a new amendment moves the validator.
assert.equal(buildAtom(changes, options), xml);
assert.equal(etagOf(xml), etagOf(buildAtom(changes, options)));
const later = [{ ...changes[0], detectedAt: '2026-10-14T18:00:00Z' }, changes[1]];
assert.notEqual(etagOf(buildAtom(later, options)), etagOf(xml));
assert.equal(kids(parseXml(buildAtom(later, options)), 'entry')[0].children.find((c) => c.name === 'id')!.text, ids[0]);
assert.match(etagOf(xml), /^"[0-9a-f]+-[0-9a-f]+"$/);

// An empty feed is still a valid feed, updated at generation time.
const empty = parseXml(buildAtom([], options));
assert.equal(kids(empty, 'entry').length, 0);
assert.equal(kids(empty, 'updated')[0].text, '2026-10-15T00:00:00Z');

// A filtered feed has its own id and its own self link.
const pl = parseXml(buildAtom(changes, { ...options, selfPath: '/changes.atom?country=PL', pagePath: '/changes?country=PL' }));
assert.notEqual(kids(pl, 'id')[0].text, kids(feed, 'id')[0].text);
assert.equal(kids(pl, 'link').find((l) => l.attrs.rel === 'self')!.attrs.href, 'https://defencegatehub.com/changes.atom?country=PL');

// ---- pieces ----
assert.equal(xmlText('a & b < c > "d"\u0000\u001F'), 'a &amp; b &lt; c &gt; &quot;d&quot;');
assert.equal(rfc3339('2026-10-14T06:20:11.512Z'), '2026-10-14T06:20:11Z');
assert.equal(rfc3339('not a date'), '1970-01-01T00:00:00Z');
assert.equal(tagId('https://example.org', 'changes', 'all'), 'tag:example.org,2026:changes:all');
assert.equal(tagId('not a url', 'x'), 'tag:defencegatehub.com,2026:x');
assert.equal(entryTitle(changes[1]).startsWith('New: '), true);

// ---- filters of the page and of the feed ----
assert.deepEqual(parseChangeFilters({}), { country: undefined, scope: undefined, page: 1, pageSize: 25 });
assert.deepEqual(parseChangeFilters({ country: 'pl,fr', scope: 'supply', page: '3' }), { country: ['PL', 'FR'], scope: 'supply', page: 3, pageSize: 25 });
assert.deepEqual(parseChangeFilters({ country: 'ZZ', scope: 'nonsense' }), { country: undefined, scope: undefined, page: 1, pageSize: 25 });
assert.equal(toChangeQuery({}), '');
assert.equal(toChangeQuery({ country: ['PL'], scope: 'core', page: 2 }), '?country=PL&scope=core&page=2');

// ---- the mock API's answer has the API's shape and window ----
const ref = new Date('2026-10-12T08:00:00Z');
const mock = queryChanges({ pageSize: 50 }, ref);
assert.equal(mock.windowDays, 14);
assert.equal(mock.total, mock.items.length);
assert.equal(mock.counts.new + mock.counts.amended, mock.total);
assert.ok(mock.items.every((c) => c.id.startsWith(`${c.tender.id}-`) && new Date(c.detectedAt) <= ref));
assert.ok(mock.items.every((c) => (c.kind === 'new') === (c.changes.length === 0)));
assert.ok(mock.items.some((c) => c.kind === 'amended'), 'the mock has amendments');
assert.equal(new Set(mock.items.map((c) => c.id)).size, mock.items.length, 'one entry per notice per day');
assert.deepEqual(queryChanges({ country: ['XX'] }, ref).items, []);

console.log('atom.check: ok');
