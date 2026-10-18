/**
 * Self-check of the funding frictions of 16 October 2026 (ux-funding F3, F4, F6, F8, F13, F16, F5): word search,
 * the empty list's way out, the default sort of a closed list, the calendar file's openings, the feed's funding
 * entries. Not part of the app and not imported by it. Run from web/:  npm run check
 */
import assert from 'node:assert/strict';
import { buildAtom } from './atom';
import { callStatusKind, getCallDeadline } from './deadline';
import { broadenings, defaultCallSort, describeCallFilters, parseCallFilters, toQuery } from './filters';
import { funderLine } from './format';
import { buildIcs } from './ics';
import type { CalendarEntry } from './calendar';
import { parseQuery } from './text-search';
import type { Call, FundingChange } from './types';

// ---- F3: the search -------------------------------------------------------------------------------------------
const hit = (q: string, text: string, codes = '') => parseQuery(q)!.matches(text, codes);
assert.ok(hit('counter-drone', 'Counter-drone systems') && hit('counter drone', 'Counter-drone systems'));
assert.ok(hit('drone', 'Unmanned systems and counter-unmanned systems'));
assert.ok(hit('counter drone', 'Unmanned systems and counter-unmanned systems'));
assert.ok(hit('UAS', 'Unmanned systems'));
assert.ok(hit('AI', 'Cybersecure tools relying on AI') && hit('AI', 'Artificial Intelligence for decisions'));
assert.ok(!hit('AI', 'Protection against threats, available while maintaining services'));
assert.ok(hit('AI for logistics', 'Artificial intelligence in military mobility'));
assert.ok(hit('logistic', 'Military logistics') && hit('fund', 'European Defence Fund') && !hit('fund', 'Refund'));
assert.ok(hit('Białystok', 'Oddział w Bialystok') && hit('Kobenhavn', 'København'));
assert.ok(hit('HORIZON-oth', 'Something', 'HORIZON-other') && !hit('HORIZON-oth', 'HORIZON-other', ''));
assert.equal(parseQuery('---'), null);
assert.deepEqual(parseQuery('counter-drone')!.terms, ['counter', 'drone']);
assert.deepEqual(parseQuery('counter-drone')!.alsoSearched, ['uas', 'uav', 'unmanned', 'rpas']);
assert.deepEqual(parseQuery('drone uav')!.alsoSearched.filter((a) => a === 'uav' || a === 'drone'), []);

// ---- F13: a closed list leads with the newest deadline; the URL stays short and round-trips -----------------------
assert.equal(defaultCallSort('closed'), 'deadline-desc');
assert.equal(defaultCallSort('open'), 'deadline-asc');
assert.equal(parseCallFilters({ status: 'closed' }).sort, 'deadline-desc');
assert.equal(toQuery(parseCallFilters({ status: 'closed' })), '?status=closed');
assert.equal(parseCallFilters({ status: 'closed', sort: 'deadline-asc' }).sort, 'deadline-asc');
assert.equal(toQuery(parseCallFilters({ status: 'closed', sort: 'deadline-asc' })), '?status=closed&sort=deadline-asc');
assert.equal(toQuery(parseCallFilters({ status: 'open', sort: 'deadline-desc' })), '?sort=deadline-desc');
assert.equal(toQuery(parseCallFilters({})), '');

// ---- F4: the empty list names what was asked and offers the way out ----------------------------------------------
const asked = parseCallFilters({ q: 'counter-drone', programme: 'EDF', status: 'closed' });
assert.deepEqual(describeCallFilters(asked), ['the search “counter-drone”', 'status Closed', 'programme EDF']);
const ways = broadenings(asked);
assert.deepEqual(ways.map((w) => w.label), [
  'without the search “counter-drone”', 'in all statuses, closed ones too', 'in every programme']);
assert.equal(toQuery(ways[0].filters), '?programme=EDF&status=closed');
assert.equal(toQuery(ways[1].filters), '?q=counter-drone&programme=EDF&status=all');
assert.equal(toQuery(ways[2].filters), '?q=counter-drone&status=closed');
assert.deepEqual(broadenings(parseCallFilters({ status: 'all' })), []);

// ---- F6: who pays, and the programme in full ----------------------------------------------------------------------
assert.equal(funderLine({ funder: 'European Commission', programmeName: 'European Defence Fund' }), 'European Commission · European Defence Fund');
assert.equal(funderLine({ funder: 'Vinnova', programmeName: 'Vinnova' }), 'Vinnova');

// ---- F1, F8: the status of a call the source calls forthcoming ------------------------------------------------------
const ref = new Date('2026-10-16T12:00:00Z');
const call = (over: Partial<Call>): Call => ({
  id: '130', slug: '130-biotech', programme: 'HORIZON', programmeName: 'Horizon Europe', funder: 'European Commission', callId: 'HORIZON-EIC-2026',
  topicId: 'HORIZON-EIC-2026-PATHFINDERCHALLENGES-01', title: 'Biotechnology for Healthy Ageing', titleLanguage: 'en', originalTitle: null,
  originalLanguage: null, regime: 'dual-use', funderCountry: 'EU', issuer: null, status: 'open', sourceStatus: 'forthcoming',
  openingDate: '2026-10-01T00:00:00Z', deadline: '2026-10-28T21:59:59Z', deadlineIsDate: true, budget: null, budgetScope: null, actionType: null,
  fundingRate: null, scope: [], eligibility: [], publishedAt: null, firstSeenAt: '2026-09-01T06:00:00Z', lastSeenAt: '2026-10-16T04:20:00Z',
  source: { sourceId: 'eu_portal', sourceName: 'EU Funding & Tenders Portal', url: null, retrievedAt: '2026-10-16T04:20:00Z', licence: '', attribution: '' },
  ...over,
});
const served = call({});
const d = getCallDeadline(served, ref);
// The API serves it open, so it is "Closing soon" (12 days), not "Opening date passed".
assert.equal(callStatusKind(served.status, d.state, served.openingDate, ref), 'soon');
assert.equal(d.dateOnly, true);
// Still forthcoming with a passed opening day and no deadline: the pill says the date passed.
assert.equal(callStatusKind('forthcoming', 'none', '2026-10-01T00:00:00Z', ref), 'pending');

// ---- F16: openings and planned deadlines are events of their own -------------------------------------------------
const entry = (over: Partial<CalendarEntry>): CalendarEntry => ({
  key: 'funding-9', kind: 'funding', event: 'deadline', id: '9', title: 'Maturing projects', href: '/funding/9-maturing', deadline: '2026-12-15T21:59:59Z',
  dateOnly: true, when: '15 Dec 2026 (date only)', who: 'European Commission', country: 'EU', sourceName: 'EU Funding & Tenders Portal', note: null, ...over,
});
const ics = buildIcs([
  entry({ key: 'funding-9-opens', event: 'opens', deadline: '2026-11-03T00:00:00Z', when: '3 Nov 2026 (date only)' }),
  entry({ planned: true }),
  entry({ key: 'funding-10', id: '10', title: 'Open now' }),
], new Date('2026-10-16T10:00:00Z'));
const uids = [...ics.matchAll(/UID:(.*)\r\n/g)].map((m) => m[1]);
assert.deepEqual(uids, ['funding-9-opens@defencegatehub.com', 'funding-9@defencegatehub.com', 'funding-10@defencegatehub.com']);
assert.ok(ics.includes('SUMMARY:Opens: Maturing projects'));
assert.ok(ics.includes('SUMMARY:Deadline\\, call not open yet: Maturing projects'));
assert.ok(ics.includes('SUMMARY:Deadline: Open now'));
assert.ok(ics.includes('DTSTART;VALUE=DATE:20261103'));
const unfolded = ics.replace(/\r\n /g, '');
assert.ok(unfolded.includes('No time is published\\; the call documents we have read set the cut-off at 17:00 Brussels time'), 'an EU portal call says what its documents give');
assert.ok(unfolded.includes('Planned opening 3 Nov 2026 (date only). The source may move it.'));

// ---- F5: funding entries in the feed, under their own categories -------------------------------------------------
const funding: FundingChange[] = [
  { id: 'call-9-20261015', kind: 'call-new', day: '2026-10-15', detectedAt: '2026-10-15T06:00:00Z', changes: [], call: call({ id: '9', slug: '9-maturing', title: 'Maturing <projects>' }) },
  { id: 'call-130-20261016', kind: 'call-amended', day: '2026-10-16', detectedAt: '2026-10-16T06:01:00Z',
    changes: [{ field: 'deadline_at', label: 'Deadline', before: '2026-10-28', after: '2026-11-12' }], call: call({}) },
];
const atom = buildAtom([], { origin: 'https://defencegatehub.com', selfPath: '/changes.atom', pagePath: '/changes', title: 't', subtitle: 's', generatedAt: '2026-10-16T00:00:00Z' }, funding);
assert.ok(atom.includes('<category term="call-new"/>') && atom.includes('<category term="call-amended"/>'));
assert.ok(atom.includes('<link rel="alternate" type="text/html" href="https://defencegatehub.com/funding/9-maturing"/>'));
assert.ok(atom.includes('New funding call: Maturing &lt;projects&gt;'));
assert.ok(atom.includes('Deadline: 2026-10-28 to 2026-11-12'));
assert.ok(atom.includes('<updated>2026-10-16T06:01:00Z</updated>\n  <link rel="self"'));
assert.ok(atom.includes('tag:defencegatehub.com,2026:change:call-9-20261015'));

console.log('funding.check: ok');
