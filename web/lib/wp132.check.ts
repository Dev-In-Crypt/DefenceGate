/**
 * Self-check of WP-132 (round-7 funding audit of 25 October 2026): a call the source stopped listing, the
 * closing day, the programme under the title, the feed's deadline, and a university on a call for companies (RAPID).
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { CLOSING_DAY_LABEL, callStatusKind, closingDayNote, getCallDeadline } from './deadline';
import { check, type EligibilityFacts } from './eligibility-check';
import { buildFundingAtom } from './funding-feed';
import { formatDateLabelledUtc, funderLine } from './format';
import type { Call } from './types';

const call = (over: Partial<Call>): Call => ({
  id: '128', slug: '128-advanced-materials', programme: 'HORIZON', programmeName: 'Horizon Europe', funder: 'European Commission',
  callId: 'HORIZON-EIC-2026-PATHFINDERCHALLENGES-01', topicId: 'HORIZON-EIC-PATHFINDERCHALLENGES-01-01', title: 'Advanced materials',
  titleLanguage: 'en', originalTitle: null, originalLanguage: null, regime: 'dual-use', funderCountry: 'EU', issuer: null, status: 'open',
  sourceStatus: 'open', openingDate: '2026-06-02T00:00:00Z', deadline: '2026-10-28T22:59:59Z', deadlineIsDate: true, budget: null, budgetScope: null,
  actionType: null, fundingRate: null, scope: [], eligibility: [], publishedAt: null, firstSeenAt: '2026-09-01T06:00:00Z',
  lastSeenAt: '2026-10-25T04:20:00Z',
  source: { sourceId: 'eu_portal', sourceName: 'EU Funding & Tenders Portal', url: null, retrievedAt: '2026-10-25T04:20:00Z', licence: '', attribution: '' },
  ...over,
});
// The CSV (lib/export.ts callRow, which reads the API module) is checked by e2e/wp132-api.spec.ts against the fake API.

// ---- 1. a call the source stopped listing: its own status, never "Open"
const gone = call({ status: 'unlisted', lastSeenAt: '2026-10-07T04:20:17Z', deadline: '2027-02-02T22:59:59Z' });
const ref = new Date('2026-10-25T12:00:00Z');
const dg = getCallDeadline(gone, ref);
assert.equal(callStatusKind(gone.status, dg.state, gone.openingDate, ref), 'unlisted');
assert.equal(dg.state, 'closed', 'no countdown, no ICS, no apply summary');
assert.equal(dg.countdown, 'No longer listed');

// ---- 11. the closing day: the hour where it is known, a warning where it is not
const lastDay = new Date('2026-10-28T18:00:00Z');                 // 19:00 Brussels: past the documents' usual 17:00, before midnight
const dateOnly = getCallDeadline(call({}), lastDay);
assert.equal(dateOnly.label, CLOSING_DAY_LABEL);
assert.equal(dateOnly.countdown, 'Today');
assert.equal(closingDayNote(dateOnly, 'EU'), CLOSING_DAY_LABEL);
assert.equal(getCallDeadline(call({}), new Date('2026-10-27T18:00:00Z')).label, 'Closes tomorrow', 'only on the day itself');
const timed = getCallDeadline(call({ deadline: '2026-10-28T16:00:00Z', deadlineIsDate: false }), new Date('2026-10-28T09:00:00Z'));
assert.equal(timed.label, 'Closes today');
assert.equal(closingDayNote(timed, 'EU'), 'Closes today, 17:00 CET (Brussels)');
assert.equal(closingDayNote(getCallDeadline(call({ deadline: '2026-10-29T16:00:00Z', deadlineIsDate: false }), new Date('2026-10-28T09:00:00Z')), 'EU'), null);

// ---- 10. an opening date is a date: no "UTC"
assert.equal(formatDateLabelledUtc('2025-11-06T00:00:00Z'), '6 Nov 2025 (date only)');

// ---- 8. the programme an EDIP call is under, under its title (the portal files it under the European Defence Fund)
assert.equal(funderLine({ funder: 'European Commission', programmeName: 'European Defence Fund', programme: 'EDIP' }),
  'European Commission · European Defence Industry Programme');
assert.equal(funderLine({ funder: 'European Commission', programmeName: 'European Defence Fund', programme: 'EDF' }),
  'European Commission · European Defence Fund');

// ---- 2. the Atom feed says the stated time, and "date only" only for a date
const feed = (c: Call) => buildFundingAtom([c], { origin: 'https://x.test', query: '', describe: 'all', total: 1, generatedAt: '2026-10-25T00:00:00Z' });
assert.match(feed(call({})), /Deadline 28 Oct 2026 \(date only\): the source gives a day and no time\./);
assert.match(feed(call({ deadline: '2027-01-14T16:00:00Z', deadlineIsDate: false })), /Deadline 14 Jan 2027, 16:00 UTC\./);

// ---- 7. a university on a call for companies with a group staff cap (RAPID): blocked, as backend/dgate/verdict.py says
const rapid = { max_group_headcount: { value: 1999, note: 'The consolidated staff count must be under 2000.', quote: '', confidence: 1, scope: 'call_document' } } as unknown as EligibilityFacts;
const group = (p: Parameters<typeof check>[1]) => check(rapid, p).lines.find((l) => l.key === 'group')!;
const base = { country: 'PL', orgType: 'large' as const, hasPartners: '' as const, controlledAbroad: 'no' as const };
assert.equal(group({ ...base, kind: 'university', size: { min: 2000, max: Infinity } }).verdict, 'no');
assert.match(group({ ...base, kind: 'university', size: { min: 2000, max: Infinity } }).reason, /A university is not a company/);
assert.equal(group({ ...base, kind: 'research', size: { min: 0, max: 49 } }).verdict, 'check');
assert.equal(group({ ...base, orgType: 'sme', kind: 'company', size: { min: 0, max: 49 } }).verdict, 'yes');
assert.equal(group({ country: 'FR', orgType: 'university', hasPartners: '', controlledAbroad: 'no' }).verdict, 'no', 'the call page form');

console.log('wp132 checks passed');
