/**
 * Self-check of WP-31 (17 October 2026): the weekly digest (weeks, URL filter, Atom feed), the cascade filter in the
 * funding URL, and the calendar file's wording for a call with several cut-offs. Not part of the app and not imported
 * by it. Run from web/:  npm run check
 */
import assert from 'node:assert/strict';
import { etagOf } from './atom';
import type { CalendarEntry } from './calendar';
import {
  buildDigestAtom, countsSentence, digestPath, headlines, isWeek, parseDigestFilters, truncation, unknownDigestCountry, weekLabel, weekMonday,
} from './digest';
import { activeFilterCount, broadenings, describeCallFilters, ignoredFilters, parseCallFilters, toQuery } from './filters';
import { buildIcs, EU_CUT_OFF_NOTE, ROLLING_NOTE } from './ics';
import type { Digest, DigestCall, DigestTender } from './types';

// ---- weeks -------------------------------------------------------------------------------------------------------------
assert.ok(isWeek('2026-W41') && isWeek('2026-W53') && isWeek('2027-W01'));
for (const bad of ['2026-W54', '2026-W00', '2026-41', '26-W41', '2026-W4', '', '2026-W41; DROP', '../2026-W41']) assert.equal(isWeek(bad), false, bad);
assert.equal(weekMonday('2026-W41').toISOString(), '2026-10-05T00:00:00.000Z');
assert.equal(weekMonday('2026-W01').toISOString(), '2025-12-29T00:00:00.000Z', 'ISO week 1 of 2026 starts on 29 December 2025');
assert.equal(weekMonday('2027-W01').toISOString(), '2027-01-04T00:00:00.000Z');
assert.equal(weekLabel('2026-W41'), 'Week 41: 5 to 11 October 2026');
assert.equal(weekLabel('2026-W40'), 'Week 40: 28 September to 4 October 2026');
assert.equal(weekLabel('2026-W53'), 'Week 53: 28 December to 3 January 2027');

// ---- the URL filter -----------------------------------------------------------------------------------------------------
assert.deepEqual(parseDigestFilters({}), {});
// D4: a country the digest does not list is reported, not silently dropped.
assert.equal(unknownDigestCountry({ country: 'zz' }), 'ZZ');
assert.equal(unknownDigestCountry({ country: 'pl' }), null);
assert.equal(unknownDigestCountry({}), null);
assert.equal(unknownDigestCountry({ country: '  ' }), null);
assert.deepEqual(parseDigestFilters({ country: 'ZZ' }), {});
assert.deepEqual(parseDigestFilters({ country: 'es' }), { country: 'ES' });
assert.deepEqual(parseDigestFilters({ country: ['FR', 'ES'] }), { country: 'FR' });
assert.deepEqual(parseDigestFilters({ country: 'EU' }), { country: 'EU' });
for (const bad of ['france', 'ZZ', '', '__proto__', 'constructor', "E'S"]) assert.deepEqual(parseDigestFilters({ country: bad }), {}, bad);
assert.equal(digestPath(null), '/digest');
assert.equal(digestPath('2026-W41', { country: 'ES' }), '/digest/2026-W41?country=ES');

// ---- an issue and its feed ---------------------------------------------------------------------------------------------------
const call = (over: Partial<DigestCall>): DigestCall => ({
  id: '56', slug: '56-ssri', kind: 'call-new', title: 'Practitioners <&> "procurers"\u0007', funder: 'European Commission', programmeName: 'Horizon Europe',
  funderCountry: 'EU', status: 'open', openingDate: null, deadline: '2026-11-20T00:00:00Z', deadlineIsDate: true, cascade: true,
  eligibility: 'Consortium of at least 3 entities from 3 countries.', eligibilityState: 'read', changes: [], ...over,
});
const tender = (over: Partial<DigestTender>): DigestTender => ({
  id: '7', slug: '7-armoured-vehicles', kind: 'new', day: '2026-10-07', title: 'Armoured vehicles', buyerName: 'Ministry of Defence', country: 'FR',
  deadline: null, estimatedValue: null, changes: [], ...over,
});
const counts = { tendersNew: 3, tendersAmended: 1, callsNew: 1, callsAmended: 0, callsOpened: 2, callsClosing: 4, cascade: 1 };
const issue = (week: string, to: string, over: Partial<Digest> = {}): Digest => ({
  week, weekFrom: `${to.slice(0, 8)}00T00:00:00Z`, weekTo: to, closingUntil: to, generatedAt: to, sectionLimit: 30, counts,
  tendersNew: [tender({})], tendersAmended: [], callsNew: [call({})], callsAmended: [], callsOpened: [], callsClosing: [],
  cascadeCalls: [call({})], cascadeOpenNow: 2, country: null, previousWeek: null, nextWeek: null, ...over,
});
const o = { origin: 'https://defencegatehub.com', generatedAt: '2026-10-17T00:00:00Z' };
const issues = [issue('2026-W41', '2026-10-12T00:00:00Z'), issue('2026-W40', '2026-10-05T00:00:00Z')];
const atom = buildDigestAtom(issues, o);
assert.ok(atom.startsWith('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"'));
assert.ok(atom.trimEnd().endsWith('</feed>'));
assert.equal((atom.match(/<entry>/g) ?? []).length, 2);
assert.equal((atom.match(/<\/entry>/g) ?? []).length, 2);
const ids = [...atom.matchAll(/<id>(.*)<\/id>/g)].map((m) => m[1]);
assert.equal(new Set(ids).size, ids.length, 'ids are unique');
assert.deepEqual(ids, ['tag:defencegatehub.com,2026:digest:all', 'tag:defencegatehub.com,2026:digest:2026-W41:all', 'tag:defencegatehub.com,2026:digest:2026-W40:all']);
assert.ok(atom.includes('<updated>2026-10-12T00:00:00Z</updated>\n  <link rel="self"'), 'the feed is as new as its newest issue');
assert.ok(atom.includes('<link rel="alternate" type="text/html" href="https://defencegatehub.com/digest/2026-W41"/>'));
assert.ok(atom.includes('Practitioners &lt;&amp;&gt; &quot;procurers&quot;'), 'markup in a title is escaped');
// eslint-disable-next-line no-control-regex
assert.ok(!/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(atom), 'no control character that XML 1.0 forbids');
assert.equal(buildDigestAtom(issues, o), atom, 'the same issues give the same document');
assert.equal(etagOf(buildDigestAtom(issues, o)), etagOf(atom));
const es = buildDigestAtom([issue('2026-W41', '2026-10-12T00:00:00Z', { country: 'ES' })], { ...o, country: 'ES' });
assert.ok(es.includes('digest:2026-W41:ES') && es.includes('href="https://defencegatehub.com/digest.atom?country=ES"') && es.includes('/digest/2026-W41?country=ES'));
const empty = buildDigestAtom([], o);
assert.ok(empty.includes('<updated>2026-10-17T00:00:00Z</updated>') && !empty.includes('<entry>'), 'a feed with no issue is still a feed');

// ---- the words ---------------------------------------------------------------------------------------------------------------
assert.equal(countsSentence({ counts: { ...counts, callsNew: 1, callsOpened: 1, cascade: 0 } }),
  '1 new funding call, 1 call opened, 4 calls closing within 14 days, 3 new defence notices, 1 amended notice.');
assert.ok(countsSentence({ counts }).endsWith('; 1 with cascade funding.'));
assert.equal(truncation(30, 30), null);
assert.equal(truncation(30, 112), 'Showing the first 30 of 112.');
assert.deepEqual(headlines(issue('2026-W41', '2026-10-12T00:00:00Z'), 5),
  ['New call: Practitioners <&> "procurers"\u0007', 'New notice: Armoured vehicles']);
assert.equal(headlines(issue('2026-W41', '2026-10-12T00:00:00Z', { callsNew: Array.from({ length: 12 }, (_, i) => call({ id: String(i) })) }), 8).length, 8);

// ---- the cascade filter in the funding URL --------------------------------------------------------------------------------------
assert.equal(parseCallFilters({ cascade: 'true' }).cascade, true);
for (const bad of ['false', 'yes', '1', '']) assert.equal(parseCallFilters({ cascade: bad }).cascade, undefined, bad);
assert.equal(toQuery(parseCallFilters({ cascade: 'true' })), '?cascade=true');
assert.equal(toQuery(parseCallFilters({ status: 'all', cascade: 'true' })), '?status=all&cascade=true');
assert.equal(toQuery(parseCallFilters({})), '', 'the default URL stays short');
assert.equal(activeFilterCount(parseCallFilters({ cascade: 'true' })), 1);
assert.ok(describeCallFilters(parseCallFilters({ cascade: 'true' })).includes('financial support to third parties'));
const loosened = broadenings(parseCallFilters({ cascade: 'true' })).map((w) => w.label);
assert.ok(loosened.includes('without the financial-support filter'));
assert.deepEqual(ignoredFilters({ cascade: 'false' }, 'funding'), ['Ignored filter: cascade=false (use true)']);
assert.deepEqual(ignoredFilters({ cascade: 'true' }, 'funding'), []);

// ---- the calendar file: a call with several cut-offs does not claim an end -----------------------------------------------------------
const entry = (over: Partial<CalendarEntry>): CalendarEntry => ({
  key: 'funding-24', kind: 'funding', event: 'deadline', id: '24', title: 'EIC Accelerator', href: '/funding/24-eic', deadline: '2026-11-04T22:59:59Z',
  dateOnly: true, when: '4 Nov 2026 (date only)', who: 'European Commission', country: 'EU', sourceName: 'EU Funding & Tenders Portal', note: null, ...over,
});
const ics = buildIcs([entry({ rolling: true, note: ROLLING_NOTE }), entry({ key: 'funding-26', id: '26', title: 'Single stage' })], new Date('2026-10-17T10:00:00Z'))
  .replace(/\r\n /g, '');
assert.ok(ics.includes('SUMMARY:Cut-off: EIC Accelerator'));
assert.ok(ics.includes('SUMMARY:Deadline: Single stage'));
assert.ok(ics.includes('Cut-off 4 Nov 2026 (date only).') && ics.includes('several cut-offs') && ics.includes('next cut-off'));
assert.ok(!ics.includes('Latest cut-off'), 'the stored date is the next cut-off, not the latest (V-B C2)');
// C1: an EU portal call is an all-day event that says the cut-off is 17:00 Brussels; the notes do not push the link out of the text.
const eu = ics.split('BEGIN:VEVENT').find((e) => e.includes('UID:funding-24@'))!;
assert.ok(eu.includes('DTSTART;VALUE=DATE:20261104') && eu.includes('17:00 Brussels time') && eu.includes('https://defencegatehub.com/funding/24-eic') && !eu.includes('…'));
assert.ok(EU_CUT_OFF_NOTE.includes('17:00 Brussels'));
// ... and another source's date-only deadline keeps the plain sentence.
const plain = buildIcs([entry({ sourceName: 'Vinnova', key: 'funding-27', id: '27' })], new Date('2026-10-17T10:00:00Z')).replace(/\r\n /g, '');
assert.ok(plain.includes('The source publishes a day and no time.') && !plain.includes('17:00'));

console.log('digest.check: ok');
