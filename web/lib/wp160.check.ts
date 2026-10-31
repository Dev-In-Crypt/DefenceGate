// WP-160 self-check: every row says where its end date comes from (each basis pinned), a renewal is said apart, the list's filters
// and links, the gate states, the coverage line from the data and the CSV. Run: node scripts/run-checks.mjs
import assert from 'node:assert/strict';
import {
  basisText, coverageLine, endingCsvRows, endingHref, endingQuery, endingState, parseEndingFilters, periodLine, renewalText,
  type EndingItem,
} from './contract-period';
import { describeFilters, searchHref } from './account-format';
import type { ContractPeriod } from './types';

const none: ContractPeriod = { start: null, end: null, endBasis: null, estimatedFrom: null, duration: null, durationUnit: null, renewal: null, renewalsMax: null };

// each basis, in words
assert.equal(periodLine({ ...none, start: '2026-04-01', end: '2027-03-31', endBasis: 'stated', renewal: true, renewalsMax: 2 }),
  '1 Apr 2026 – 31 Mar 2027 · stated end date · renewal options: up to 2 renewals');
assert.equal(periodLine({ ...none, start: '2026-04-01', end: '2027-04-01', endBasis: 'computed', duration: 12, durationUnit: 'MONTH' }),
  '1 Apr 2026 – 1 Apr 2027 · 12 months · computed from start + duration');
assert.equal(periodLine({ ...none, end: '2027-01-15', endBasis: 'estimated', estimatedFrom: 'award_published', duration: 6, durationUnit: 'MONTH' }),
  '? – 15 Jan 2027 · 6 months · estimated: award notice publication date + duration');
assert.equal(periodLine({ ...none, duration: 1, durationUnit: 'YEAR' }), '1 year · duration only, no start: no end date');
assert.equal(basisText({ ...none, renewal: true }), 'no end date stated');
assert.equal(renewalText({ renewal: true, renewalsMax: 1 }), 'renewal options: up to 1 renewal');
assert.equal(renewalText({ renewal: true, renewalsMax: null }), 'renewal possible');
assert.equal(renewalText({ renewal: null, renewalsMax: null }), null);

// filters: a window of 3, 6 or 12 months (12 by default), estimates only when asked for
const f = parseEndingFilters({ within: '6', country: 'Germany', cpv: '35x41', buyer: '42', estimated: 'true', page: '2' });
assert.deepEqual(f, { within: 6, country: 'Germany', cpv: '3541', buyer: '42', estimated: true, page: 2 });
assert.deepEqual(parseEndingFilters({ within: '5', buyer: 'x; drop' }), { within: 12, country: '', cpv: '', buyer: '', estimated: false, page: 1 });
assert.equal(endingQuery({ ...f, country: 'DE' }), 'within=6&country=DE&cpv=3541&buyer=42&estimated=true');
assert.equal(endingHref(parseEndingFilters({})), '/tenders/ending');
assert.equal(endingHref(f, { page: 1 }, '/tenders/ending/export.csv'), '/tenders/ending/export.csv?within=6&country=Germany&cpv=3541&buyer=42&estimated=true');

// beyond the first rows
assert.equal(endingState(200), 'full');
assert.equal(endingState(402), 'plan');
assert.equal(endingState(401), 'signin');
assert.equal(endingState(0), 'signin');

// the coverage line names what the data holds, never a fixed list
const name = (c: string) => ({ DE: 'Germany', FR: 'France' }[c] ?? c);
assert.equal(coverageLine([{ country: 'DE', dated: 9613, estimated: 0 }, { country: 'FR', dated: 1423, estimated: 12 }, { country: 'PL', dated: 0, estimated: 3 }], name),
  'Contract periods we can date come from notices of Germany (9,613), France (1,423). Other countries\' notices state none we hold yet. 15 more award notices state only a duration: their end is an estimate, shown only when you ask for estimates.');
assert.ok(coverageLine([{ country: 'DE', dated: 2, estimated: 1 }], name).endsWith(' 1 more award notice states only a duration: its end is an estimate, shown only when you ask for estimates.'));
assert.equal(coverageLine([], name),'No notice we hold states a contract period we can date yet.');

// a saved search of contracts ending soon links to the list and says its window
assert.equal(searchHref('ending', { within: '6', country: 'DE', q: 'dropped' }), '/tenders/ending?country=DE&within=6');
assert.deepEqual(describeFilters('ending', { within: '6', country: 'DE' }), ['Ending within 6 months', 'Buyer country: Germany', 'Stated and computed ends']);

// the CSV says the basis on every row
const item = {
  id: '7', slug: '7-x', noticeId: '7-2026', title: '=Vehicle maintenance', buyerName: 'Bundeswehr', country: 'DE', cpv: '50110000',
  source: { url: 'https://ted.example/7' }, awardedTo: [{ name: 'Acme GmbH', slug: null, country: 'DE' }],
  contractPeriod: { ...none, start: '2026-04-01', end: '2027-04-01', endBasis: 'computed', duration: 12, durationUnit: 'MONTH' },
} as unknown as EndingItem;
assert.deepEqual(endingCsvRows([item], 'https://site.test')[0], ['=Vehicle maintenance', 'Bundeswehr', 'DE', '50110000', '2026-04-01', '2027-04-01',
  'computed from start + duration', '12 months', null, 'Acme GmbH', '7-2026', 'https://ted.example/7', 'https://site.test/tenders/7-x']);

console.log('wp160 checks ok');
