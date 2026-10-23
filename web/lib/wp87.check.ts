/**
 * Self-check of WP-87 (UX audit of 22 October 2026, section 2: correctness and trust): number pairs that agree or say why not, the
 * calendar and the change feed with the list's filters, an open notice that is never "Closed", core defence and defence calls
 * first with plain scope names, the copy fixes, suspect values, the source status, the CPV division names.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { calendarCounts, calendarNotices, feedLine, tenderOnly } from './calendar-counts';
import { approachSentence } from './demand';
import { splitByRegime } from './digest';
import {
  CHANGE_PARAMS, defaultTenderSort, dualUseStart, ignoredFilters, parseChangeFilters, parseTenderFilters, toChangeQuery, toTenderQuery, unknownParams,
} from './filters';
import { amendmentsShown, profileYearBars } from './market';
import { contributionMissing } from './networks';
import { sourceFreshness, updatedLine } from './source-status';
import { cpvDivisionLabel, SCOPE_CHOICES, TENDER_SCOPES } from './taxonomy';
import { firstDeadlineLabel, tenderStatusView } from './tender-status';
import { listStamps } from './list-count';
import { suspectLine, SUSPECT_NOTE, SUSPECT_VALUE_MAX } from './value-totals';
import { buildIcs, ICS_MAX_EVENTS } from './ics';
import type { CalendarEntry } from './calendar-tenders';

// ---- 1. the calendar's numbers beside the lists'
const p = { kind: 'all' as const, countries: [], tender: {} };
const both = calendarCounts({ tendersOk: true, callsOk: true, tendersHeld: 1486, longRunning: 96, openCalls: Array(63).fill('EU') }, p,
  { tenders: 1390, calls: 58 }, '2026-10-22');
assert.equal(both[0].text, 'Tenders: 1,390 deadlines of the 1,486 open tenders with a deadline ahead that the tenders list counts under these filters; 96 have a deadline more than 3 years ahead (framework agreements and dynamic purchasing systems that stay open) and are left off.');
assert.equal(both[0].href, '/tenders?from=2026-10-22', 'the link opens the list that counts the same notices');
assert.equal(both[1].text, 'Funding calls: 58 deadlines of the 63 open calls the funding list counts; 5 have no coming deadline (submission continues past the last cut-off, or no date is stated).');
const equal = calendarCounts({ tendersOk: true, callsOk: true, tendersHeld: 10, longRunning: 0, openCalls: [] }, { ...p, kind: 'tenders' },
  { tenders: 10, calls: 0 }, '2026-10-22');
assert.equal(equal.length, 1);
assert.match(equal[0].text, /^Tenders: 10 deadlines, every open tender with a deadline ahead/);
// a filtered calendar links the list of the same filters
const filtered = calendarCounts({ tendersOk: true, callsOk: true, tendersHeld: 3, longRunning: 0, openCalls: [] },
  { kind: 'tenders', countries: ['DE', 'PL'], tender: { cpv: ['32', '35'] } }, { tenders: 3, calls: 0 }, '2026-10-22');
assert.equal(filtered[0].href, '/tenders?country=DE%2CPL&cpv=32%2C35&from=2026-10-22');
// the feed says how many events it holds, and where a ceiling would cut
assert.equal(feedLine(1475), 'It holds every one of the 1,475 events these filters give.');
assert.equal(feedLine(6001), 'It holds the first 5,000 of the 6,001 events these filters give; narrow them for the rest.');
assert.ok(ICS_MAX_EVENTS >= 3060, 'the file holds the API\'s 3,000 tenders and every call');
const entry = (i: number): CalendarEntry => ({ key: `tender-${i}`, kind: 'tender', event: 'deadline', id: String(i), title: `T${i}`, href: `/tenders/${i}-t`,
  deadline: '2026-11-01T10:00:00Z', dateOnly: false, when: '1 Nov 2026', who: 'B', country: 'DE', sourceName: 'TED', note: null });
const big = buildIcs(Array.from({ length: 1500 }, (_, i) => entry(i)), new Date('2026-10-22T10:00:00Z'));
assert.equal((big.match(/BEGIN:VEVENT/g) ?? []).length, 1500, 'no silent cap at 500');
assert.ok(!big.replace(/\r\n /g, '').includes('This file holds the first'));
assert.ok(buildIcs([entry(1)], new Date(), { tendersBeyond: 12 }).replace(/\r\n /g, '').includes('12 open tenders with later deadlines are not in it'));

// ---- 1. one stamp, or two named ones
assert.deepEqual(listStamps({ asOf: '2026-10-22T18:02:10Z' }, { asOf: '2026-10-22T18:02:40Z' }), { list: 'Counts as of 18:02 UTC', scope: 'Counts as of 18:02 UTC' });
const two = listStamps({ asOf: '2026-10-22T18:56:00Z' }, { asOf: '2026-10-22T18:02:00Z' });
assert.equal(two.list, 'List as of 18:56 UTC');
assert.match(two.scope ?? '', /^Scope counts as of 18:02 UTC, worked out apart from the list \(as of 18:56 UTC\)/);
assert.equal(updatedLine('2026-10-22T07:29:00Z', 'Plataforma de Contratación del Sector Público'),
  'Latest run of its sources: 22 Oct 2026, 07:29 UTC (Plataforma de Contratación del Sector Público)');
assert.equal(updatedLine('2026-10-22T07:29:00Z', null), 'Latest run of its sources: 22 Oct 2026, 07:29 UTC');

// ---- 1. a buyer's years add up to its total; the amendment share waits for six months of watching
const bars = profileYearBars({ perYear: [{ year: 2025, count: 3 }, { year: 2026, count: 2 }], perYearEarlier: 4, perYearUndated: 1 });
assert.deepEqual(bars.map((b) => [b.label, b.primary]), [['Before 2025', 4], ['2025', 3], ['2026', 2], ['No date', 1]]);
assert.equal(bars.reduce((n, b) => n + b.primary, 0), 10);
assert.deepEqual(profileYearBars({ perYear: [{ year: 2026, count: 2 }] }).map((b) => b.label), ['2026']);
assert.deepEqual(amendmentsShown({ observedFrom: '2026-09-10T00:00:00Z' }, '2026-10-22T00:00:00Z'), { shown: false, since: 'Sep 2026' });
assert.equal(amendmentsShown({ observedFrom: '2026-09-10T00:00:00Z' }, '2027-03-20T00:00:00Z').shown, true);
assert.equal(amendmentsShown({}, '2026-10-22T00:00:00Z').shown, false, 'an API that does not say is read as the archive start');

// ---- 2. the change list and its feed read the list's filters; nothing is dropped in silence
const cf = parseChangeFilters({ cpv: '35,34300000', q: 'radar', from: '2026-11-01', min: '1000', currency: 'eur', country: 'de' });
assert.deepEqual([cf.cpv, cf.q, cf.deadlineFrom, cf.valueMin, cf.currency, cf.country], [['35', '34300000'], 'radar', '2026-11-01', 1000, 'EUR', ['DE']]);
assert.equal(toChangeQuery(cf), '?country=DE&q=radar&cpv=35%2C34300000&from=2026-11-01&min=1000&currency=EUR');
assert.deepEqual(unknownParams({ cpvv: '35', country: 'DE', blank: '' }, CHANGE_PARAMS), ['Ignored filter: cpvv (not a filter of this page)']);
assert.ok(ignoredFilters({ cpv: 'abc' }, 'changes').some((m) => m.startsWith('Ignored filter: cpv=abc')));
assert.ok(ignoredFilters({ foo: 'x' }, 'changes').includes('Ignored filter: foo (not a filter of this page)'));
// the calendar: unknown keys, tender-only filters and funding calls
assert.deepEqual(tenderOnly({ cpv: ['35'], q: 'x' }), ['the search', 'the CPV code']);
assert.deepEqual(calendarNotices({ cpv: '35', bogus: '1' }, { kind: 'all', countries: [], tender: { cpv: ['35'] } }),
  ['Ignored filter: bogus (not a filter of this page)', 'Funding calls are not listed: the CPV code applies to tenders only.']);
assert.deepEqual(calendarNotices({ cpv: '3x' }, { kind: 'tenders', countries: [], tender: {} }), ['Ignored filter: cpv=3x (CPV codes are 2 to 8 digits)']);
assert.deepEqual(calendarNotices({ kind: 'funding', country: 'EU', view: 'month' }, { kind: 'funding', countries: ['EU'], tender: {} }), []);

// ---- 3. open is never "Closed"
const dps = { status: 'open' as const, deadline: '2028-01-01T00:00:00Z', statusNative: 'open', anomalies: ['first-deadline-passed'],
  title: 'Sistema dinámico de adquisición de repuestos' };
assert.deepEqual(tenderStatusView(dps, new Date('2026-10-22T00:00:00Z')), { kind: 'open', label: 'Open (dynamic purchasing system): first deadline passed', word: 'Open' });
assert.equal(firstDeadlineLabel({ title: 'Framework for spare parts' }), 'Open: first deadline passed');
assert.equal(tenderStatusView({ ...dps, anomalies: [] }, new Date('2026-10-22T00:00:00Z')).label, 'Open');

// ---- 4. core first, defence calls first, plain scope names
assert.equal(defaultTenderSort('open'), 'core-first');
assert.equal(defaultTenderSort(undefined), 'core-first');
assert.equal(toTenderQuery(parseTenderFilters({})), '', 'the default order is not written into the address');
assert.equal(toTenderQuery(parseTenderFilters({ sort: 'deadline-asc' })), '?sort=deadline-asc', 'the plain deadline order is a choice');
assert.deepEqual([SCOPE_CHOICES.relevant.label, SCOPE_CHOICES.core.label, SCOPE_CHOICES.supply.label],
  ['All defence', 'Military goods and works', 'Other purchases by armed forces']);
assert.equal(TENDER_SCOPES.core.label, 'Military goods and works');
assert.equal(dualUseStart([{ regime: 'defence' }, { regime: 'dual-use' }, { regime: 'dual-use' }], true), 1);
assert.equal(dualUseStart([{ regime: 'defence' }, { regime: 'dual-use' }], false), -1);
assert.equal(dualUseStart([{ regime: 'defence' }], true), -1);
const split = splitByRegime([{ id: 1, regime: 'dual-use' }, { id: 2, regime: 'defence' }, { id: 3 }]);
assert.deepEqual([split.defence.map((c) => c.id), split.dualUse.map((c) => c.id)], [[2, 3], [1]]);

// ---- 5. the winners sentence: the report's numbers, words apart
const demand = { kMin: 1, total: { winners: 365 }, approach: { winners: Array.from({ length: 38 }, (_, i) => ({ prime: i < 11 ? {} : null })), below: { winners: 0, awards: 0 }, more: { winners: 327, awards: 900 } } };
const said = approachSentence(demand as never);
assert.equal(said, '365 companies won them. The report names every one of them: the 38 with the most contracts, and every prime contractor or large defence group, under “who to approach”, and all 365 on its list of winners. 11 of those listed are marked as a prime contractor or large defence group.');
assert.ok(!/companieswould/.test(said));
// no text read with the wrong encoding in the code or the data (e-ZamГіwienia, Santa BГЎrbara)
const garbled = /[A-Za-z][\u0413\u0420\u0421][\u0400-\u040f\u0450-\u045f\u0490\u0491\u00a0-\u00bf\u2013-\u203a\u2116\u20ac]|\u00c3[\u0080-\u00bf]/;
const walk = (dir: string): string[] => readdirSync(dir).flatMap((f) => {
  const full = join(dir, f);
  return statSync(full).isDirectory() ? walk(full) : /\.(ts|tsx|json)$/.test(f) && !f.endsWith('.check.ts') ? [full] : [];
});
for (const file of [...walk('lib'), ...walk('app'), ...walk('components')]) {
  assert.ok(!garbled.test(readFileSync(file, 'utf8')), `text read with the wrong encoding in ${file}`);
}

// ---- 6. suspect values and the plain words for a missing amount
assert.equal(SUSPECT_VALUE_MAX, 1000);
assert.equal(SUSPECT_NOTE, 'value as published, probably a unit price');
assert.equal(suspectLine({ byCurrency: [], of: 3, withoutValue: 1, shared: 0, suspect: 2 }, 'contract'),
  '2 contracts state a value under 1,000 (probably a unit price, not the contract’s value) and are left out of the sums.');
assert.equal(suspectLine({ byCurrency: [], of: 3, withoutValue: 3, shared: 0 }, 'contract'), null);
assert.equal(contributionMissing(['EDF']), 'Not published per participant (EDF factsheets state no amounts)');
assert.equal(contributionMissing(['EDF', 'HORIZON']), 'Not stated');

// ---- 7. an OK run that nothing measures is not plain OK
const ref = new Date('2026-10-22T10:00:00Z');
const sedia = sourceFreshness({ id: 'eu_portal', status: 'ok', lastRunAt: '2026-10-22T04:35:00Z', coverage: null, records: 1 }, ref);
assert.equal(sedia.kind, 'ok-incremental');
assert.match(sedia.note ?? '', /No minimum is set for this source.*it fetched 1 record, reading only what changed/);
assert.equal(sourceFreshness({ id: 'ted', status: 'ok', lastRunAt: '2026-10-22T04:35:00Z', coverage: 1.2, records: 900 }, ref).kind, 'ok');

// ---- 8. every CPV division of the vocabulary has its name
const full = JSON.parse(readFileSync('lib/data/cpv-full.json', 'utf8')) as { codes: Record<string, string> };
for (const code of Object.keys(full.codes).filter((c) => /^\d{2}000000$/.test(c))) {
  assert.ok(cpvDivisionLabel(code), `division ${code.slice(0, 2)} has a name`);
}
assert.equal(cpvDivisionLabel('77'), 'Agricultural, forestry, horticultural, aquacultural and apicultural services');
for (const d of ['16', '41', '76']) assert.equal(cpvDivisionLabel(d), full.codes[`${d}000000`]);

console.log('wp87 ok');
