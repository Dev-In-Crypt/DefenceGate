/**
 * Self-check of WP-52b (the web side of the tender data fixes of the UX audit of 19 October 2026: T2, T3, T8-T11, T13, T14,
 * T16-T18). Not part of the app and not imported by it. Run with `npm run check` (scripts/run-checks.mjs), or from web/:
 *   npx tsc lib/wp52b.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/wp52b.check.js
 */
import assert from 'node:assert/strict';
import { buildAtom, feedSubtitle } from './atom';
import { entryFromItem, pageOfDay } from './calendar-tenders';
import { pageOf } from './calendar-view';
import { cpvName, cpvOwnName } from './cpv';
import cpvData from './data/cpv.json';
import { noticesIn, repeatsLabel, restOfTendersHref, truncation } from './digest';
import { defaultTenderSort, ignoredFilters, parseChangeFilters, parseTenderFilters, toChangeQuery, toTenderQuery } from './filters';
import { countsAsOf, countsNote, cutSentence, listIsCut, overlapNote, reachableTotal, scopeCountText, totalWords } from './list-count';
import * as tenderMock from './mock/tenders';
import { lateRuleSentence, sourceFreshness, statusReasonLine } from './source-status';
import { cpvDivisionLabel } from './taxonomy';
import { tenderChangedLabel } from './tender-status';
import type { CalendarItem } from './types';

const REF = new Date('2026-10-19T12:00:00Z');

// ---- T3: a capped total reads "at least", the pager stops at the cap and says so ----
assert.equal(totalWords({ total: 10000, totalCapped: true }), 'at least 10,000');
assert.equal(totalWords({ total: 41, totalCapped: true }), 'at least 41');
assert.equal(totalWords({ total: 287634, totalCapped: false }), undefined);
assert.equal(totalWords({ total: 287634 }), undefined, 'an older API sends no flag: an exact count');
assert.equal(reachableTotal({ total: 287634, maxOffset: 10000 }), 10000);
assert.equal(reachableTotal({ total: 120, maxOffset: 10000 }), 120);
assert.equal(reachableTotal({ total: 120 }), 120);
assert.equal(listIsCut({ total: 287634, maxOffset: 10000 }), true);
assert.equal(listIsCut({ total: 10000, totalCapped: true, maxOffset: 10000 }), true, 'a count that stopped at the cap is "at least" it');
assert.equal(listIsCut({ total: 10000, totalCapped: false, maxOffset: 10000 }), false, 'exactly 10,000 is all of it');
assert.equal(listIsCut({ total: 41, totalCapped: true, maxOffset: 10000 }), false, 'a lower bound far under the cap is not a cut');
assert.equal(listIsCut({ total: 500 }), false);
assert.match(cutSentence({ total: 287634, maxOffset: 10000 }) ?? '', /^The list shows the first 10,000 tenders of this search\. Narrow it with the filters/);
assert.equal(cutSentence({ total: 500, maxOffset: 10000 }), null);
// The last page the pager can reach is page 1,000 of 10 (position 9,991 to 10,000), never page 28,764.
assert.equal(Math.ceil(reachableTotal({ total: 287634, maxOffset: 10000 }) / 10), 1000);

// ---- T13: the scope counts say when they were worked out, how many notices two of them share, and when they are "at least" ----
assert.equal(scopeCountText(1522, false), ' (1,522)');
assert.equal(scopeCountText(1522, undefined), ' (1,522)');
assert.equal(scopeCountText(12000, true), ' (at least 12,000)');
assert.equal(countsAsOf('2026-10-19T11:05:30Z'), 'Counts as of 11:05 UTC');
assert.equal(countsAsOf('2026-10-19T00:00:00Z'), 'Counts as of 00:00 UTC', 'midnight is a time, not "time not stated"');
assert.equal(countsAsOf(undefined), null);
assert.equal(countsAsOf('not a date'), null);
assert.equal(overlapNote({ overlap: 0 }), null);
assert.equal(overlapNote({}), null);
// WP-121: the same note in the words of the filter's labels (was "Core and supplies add up to 46 more than the first count: 46 supply notices
// are the national copy of a core notice")
assert.match(overlapNote({ overlap: 46 }) ?? '', /^Military goods and works and Other purchases by armed forces add up to 46 more than All defence: 46 notices are in both \(the national copy of a notice of military goods and works\)/);
assert.match(overlapNote({ overlap: 1 }) ?? '', /: 1 notice is in both \(the national copy/);
assert.equal(countsNote({ asOf: '2026-10-19T11:05:00Z', overlap: 46 })?.startsWith('Counts as of 19 Oct 2026, 11:05 UTC. Military goods and works and Other purchases by armed forces add up to 46 more'), true);
assert.equal(countsNote({ asOf: '2026-10-19T11:05:00Z' }), 'Counts as of 19 Oct 2026, 11:05 UTC.', 'the home stamp has its date (WP-59, NEW-13)');
assert.equal(countsNote(null), null);
// 1,522 = 294 + 1,274 - 46: the three counts and the note agree.
assert.equal(294 + 1274 - 46, 1522);

// ---- T8: Planned is a status of its own ----
assert.equal(parseTenderFilters({ status: 'planned' }).status, 'planned');
assert.equal(parseTenderFilters({ status: 'planned' }).sort, 'deadline-desc', 'a planned list runs newest deadline first, like closed (the API default)');
assert.equal(defaultTenderSort('planned'), 'deadline-desc');
assert.equal(defaultTenderSort('open'), 'core-first');   // WP-87: the open list leads with the military goods and works
// WP-106 (p02, p04, p07): All is its open notices, then the rest newest deadline first (it read the rest oldest first: 2017 on top)
assert.equal(defaultTenderSort('all'), 'open-first');
assert.equal(toTenderQuery(parseTenderFilters({ status: 'planned' })), '?status=planned');
assert.deepEqual(ignoredFilters({ status: 'planned' }, 'tenders'), [], 'planned is a known status');
assert.equal(ignoredFilters({ status: 'upcoming' }, 'tenders').length, 1);
// The demo data: a planned notice is neither open nor closed, and `all` has it.
const ids = (status: 'open' | 'closed' | 'planned' | 'all') => tenderMock.queryTenders({ status, scope: 'all', pageSize: 100 }, REF).items;
const planned = ids('planned');
assert.ok(planned.length >= 1 && planned.every((t) => t.statusNative === 'forthcoming'));
assert.ok(ids('closed').every((t) => t.statusNative !== 'forthcoming'), 'Closed no longer shows planned notices');
assert.ok(ids('open').every((t) => t.statusNative !== 'forthcoming'));
assert.equal(ids('all').length, ids('open').length + ids('closed').length + planned.length, 'the statuses add up to All');

// ---- T9: the calendar holds every open notice the API sends; November shows its 593 ----
const item = (n: number, deadline: string, over: Partial<CalendarItem> = {}): CalendarItem => ({
  id: String(n), slug: `${n}-notice-${n}`, noticeId: `${n}-2026`, title: `Notice ${n}`, buyerName: 'Buyer', country: 'DE', deadline,
  deadlineFrom: null, scope: 'core', status: 'open', statusNative: 'open', anomalies: [], sourceName: 'TED', ...over,
});
const november = Array.from({ length: 593 }, (_, i) => item(1000 + i, `2026-11-${String(1 + (i % 30)).padStart(2, '0')}T${String(8 + (i % 9)).padStart(2, '0')}:00:00Z`));
const october = Array.from({ length: 450 }, (_, i) => item(2000 + i, `2026-10-${String(20 + (i % 12)).padStart(2, '0')}T10:00:00Z`));
const december = Array.from({ length: 406 }, (_, i) => item(3000 + i, `2026-12-${String(1 + (i % 28)).padStart(2, '0')}T10:00:00Z`));
const api = [...october, ...november, ...december].sort((a, b) => a.deadline.localeCompare(b.deadline));
assert.equal(api.length, 1449);
const entries = api.flatMap((it) => { const r = entryFromItem(it, REF); return r.entry ? [r.entry] : []; });
assert.equal(entries.length, 1449, 'nothing the API sends is dropped');
const inNovember = entries.filter((e) => e.deadline.startsWith('2026-11'));
assert.equal(inNovember.length, 593, 'November shows its 593 (the old calendar showed none: it read the 500 earliest of 1,529)');
// The agenda is paged (100 a page), so a month of 593 is six pages, every entry once, in time order.
const pages = Array.from({ length: pageOf(inNovember, 1, 100).pages }, (_, i) => pageOf(inNovember, i + 1, 100).items);
assert.equal(pages.length, 6);
assert.deepEqual(pages.map((p) => p.length), [100, 100, 100, 100, 100, 93]);
assert.equal(new Set(pages.flat().map((e) => e.key)).size, 593);
assert.ok(pages.every((p) => p.length <= 100), 'no page is longer than its budget');
// "+N more" of a day leads to the page that holds that day, and the entry is on it.
for (const day of ['2026-11-01', '2026-11-15', '2026-11-30']) {
  const at = pageOfDay(inNovember, day, 100);
  assert.ok(pageOf(inNovember, at, 100).items.some((e) => e.deadline.startsWith(day)), day);
}
assert.equal(pageOfDay(inNovember, '2026-12-25', 100), 1, 'a day with no entry: page 1');
// What is not a date to plan around: a notice that is not open any more, a deadline over three years ahead.
assert.equal(entryFromItem(item(1, '2026-10-01T10:00:00Z'), REF).entry, null, 'a deadline that has passed');
assert.deepEqual(entryFromItem(item(2, '2031-05-01T10:00:00Z', { anomalies: ['deadline-more-than-3y'] }), REF), { entry: null, long: true });
assert.equal(entryFromItem(item(3, '2026-11-20T10:00:00Z', { statusNative: 'awarded', status: 'closed' }), REF).entry, null);
const dated = entryFromItem(item(4, '2026-11-20T00:00:00Z', { deadlineFrom: 'ted_twin' }), REF).entry;
assert.equal(dated?.dateOnly, true, 'a deadline at 00:00 UTC is a date, as on the notice page');
assert.equal(dated?.href, '/tenders/4-notice-4');
assert.equal(dated?.who, 'Buyer');
// The demo calendar is the same shape.
const demo = tenderMock.queryCalendar(REF);
assert.ok(demo.items.length > 0 && demo.items.every((i) => i.status === 'open' && i.deadline));
assert.equal(demo.total, demo.items.length);

// ---- T10: the digest ----
assert.equal(noticesIn([{ repeats: 13 }, {}, { repeats: 1 }, { repeats: undefined }]), 16, 'a row that stands for 13 notices is 13');
assert.equal(noticesIn([]), 0);
assert.equal(repeatsLabel(13), '×13');
assert.equal(repeatsLabel(1), null);
assert.equal(repeatsLabel(undefined), null);
assert.equal(truncation(noticesIn([{ repeats: 13 }, { repeats: 36 }]), 873), 'Showing the first 49 of 873.', '30 rows stand for 49 notices');
assert.equal(restOfTendersHref('2026-W42', 'new'), '/changes?week=2026-W42&kind=new');
assert.equal(restOfTendersHref('2026-W42', 'amended', 'PL'), '/changes?week=2026-W42&kind=amended&country=PL');
assert.equal(restOfTendersHref('2026-W42', 'new', 'EU'), '/changes?week=2026-W42&kind=new', 'EU is the Commission’s own calls: no notice has it');
// The link works: the change list reads the week and the kind, and sends them to the API.
const week = parseChangeFilters({ week: '2026-W42', kind: 'new', country: 'PL' });
assert.deepEqual([week.week, week.kind, week.country], ['2026-W42', 'new', ['PL']]);
assert.equal(toChangeQuery(week), '?country=PL&week=2026-W42&kind=new');
assert.equal(toChangeQuery({ ...week, page: 3 }), '?country=PL&week=2026-W42&kind=new&page=3');
assert.equal(parseChangeFilters({ week: '2026-W99' }).week, undefined, 'not a week of the year');
assert.equal(parseChangeFilters({ week: '42' }).week, undefined);
assert.equal(parseChangeFilters({ week: '2026-W42&x=1' }).week, undefined);
assert.equal(parseChangeFilters({ kind: 'other' }).kind, undefined);
assert.equal(toChangeQuery(parseChangeFilters({})), '', 'the default list is still the cacheable one');
assert.equal(tenderMock.weekAvailable('2026-W41', new Date('2026-10-12T08:00:00Z')), true);
// WP-90 (rewritten): the week under way is listed up to now ("this week so far"); a week to come is not
assert.equal(tenderMock.weekAvailable('2026-W42', new Date('2026-10-12T08:00:00Z')), true, 'the week under way');
assert.equal(tenderMock.weekAvailable('2026-W43', new Date('2026-10-12T08:00:00Z')), false, 'a week to come');
assert.equal(tenderMock.weekAvailable('2026-W36', REF), false, 'before the archive');
// The demo list of a week and a kind holds exactly the entries of that week and kind; the counts count both kinds.
const w41 = tenderMock.queryChanges({ week: '2026-W41', pageSize: 100 }, new Date('2026-10-12T08:00:00Z'));
const w41new = tenderMock.queryChanges({ week: '2026-W41', kind: 'new', pageSize: 100 }, new Date('2026-10-12T08:00:00Z'));
assert.equal(w41.windowDays, 7);
assert.ok(w41new.items.length > 0 && w41new.items.every((c) => c.kind === 'new'));
assert.equal(w41new.total, w41.counts.new);
assert.deepEqual(w41new.counts, w41.counts);
assert.ok(w41.items.every((c) => c.day >= '2026-10-05' && c.day <= '2026-10-11'));

// ---- T10: the Atom feed holds the window it reads, and says so only when a cap cuts it ----
assert.ok(!feedSubtitle(14, 2311, 2311).includes('holds the newest'), 'nothing is said when the feed holds the whole window');
assert.match(feedSubtitle(14, 2311, 2400), /^New defence and dual-use notices/);
assert.ok(!feedSubtitle(14, 2311, 2311).includes('2,311'));
assert.match(feedSubtitle(14, 3100, 2400), /This feed holds the newest 2,400 of the 3,100 changes; the page lists them all\.$/);
const many = tenderMock.queryChanges({ pageSize: 100 }, new Date('2026-10-12T08:00:00Z')).items;
assert.ok(many.length > 0);
const feed = buildAtom(many, { origin: 'https://example.test', selfPath: '/changes.atom', pagePath: '/changes', title: 't', subtitle: feedSubtitle(14, many.length, many.length), generatedAt: '2026-10-12T08:00:00Z' });
assert.equal((feed.match(/<entry>/g) ?? []).length, many.length, 'one entry per change it was given');

// ---- T11: the label says what the stamp is ----
assert.equal(tenderChangedLabel({ lastChangeKind: 'amendment' }), 'Last change seen at the source');
assert.equal(tenderChangedLabel({ lastChangeKind: 'first_seen' }), 'First seen by us');
assert.equal(tenderChangedLabel({ lastChangeKind: null }), 'First seen by us');
assert.equal(tenderChangedLabel({}), 'First seen by us', 'an API that does not say gets the careful label');
const amended = tenderMock.allTenders(REF).filter((t) => t.versionCount > 1);
assert.ok(amended.length > 0 && amended.every((t) => tenderChangedLabel(t.source) === 'Last change seen at the source'));
assert.ok(tenderMock.allTenders(REF).filter((t) => t.versionCount === 1).every((t) => tenderChangedLabel(t.source) === 'First seen by us'));

// ---- T16 / T18: a source is late for its own rhythm; a partial run says why ----
// A monthly source that ran nine days ago is not late (CORDIS and EDF were "Stale" after three days, T16); it says how it is collected.
const TWENTIETH = new Date('2026-10-20T12:00:00Z');
assert.deepEqual(sourceFreshness({ id: 'cordis', status: 'ok', lastRunAt: '2026-10-10T19:10:00Z', updateFreq: 'monthly', staleAfterHours: 960, stale: false }, TWENTIETH),
  { kind: 'ok', note: 'Collected monthly, last ran 9 days ago' });
assert.deepEqual(sourceFreshness({ id: 'cordis', status: 'ok', lastRunAt: '2026-10-18T19:10:00Z', updateFreq: 'monthly', staleAfterHours: 960, stale: false }, TWENTIETH),
  { kind: 'ok', note: null }, 'ran within the three days: nothing to add');
assert.equal(sourceFreshness({ id: 'cordis', status: 'ok', lastRunAt: '2026-08-01T19:10:00Z', updateFreq: 'monthly', staleAfterHours: 960, stale: true }, TWENTIETH).kind, 'stale', 'late for a month is stale');
// The old rule would have said stale; the API says it is not.
assert.equal(sourceFreshness({ id: 'ted', status: 'ok', lastRunAt: '2026-10-10T19:10:00Z' }, TWENTIETH).kind, 'stale', 'no `stale` from the API: the daily rule');
assert.equal(sourceFreshness({ id: 'ted', status: 'ok', lastRunAt: '2026-10-10T19:10:00Z', updateFreq: 'daily', staleAfterHours: 72, stale: true }, TWENTIETH).kind, 'stale');
assert.equal(sourceFreshness({ id: 'ted', status: 'ok', lastRunAt: '2026-10-19T19:10:00Z', updateFreq: 'daily', staleAfterHours: 72, stale: false }, REF).kind, 'ok');
assert.equal(sourceFreshness({ id: 'x', status: 'ok', lastRunAt: '2026-01-10T19:10:00Z', updateFreq: 'on demand', stale: null }, REF).kind, 'ok', 'no rhythm: never late');
assert.equal(sourceFreshness({ id: 'x', status: 'ok', lastRunAt: '2026-01-10T19:10:00Z', updateFreq: 'one-off', stale: null }, REF).kind, 'one-off');
assert.equal(sourceFreshness({ id: 'x', status: 'partial', lastRunAt: '2026-10-19T08:00:00Z', stale: false }, REF).kind, 'partial');
assert.equal(statusReasonLine({ status: 'partial', statusReason: 'The source’s live feed had published nothing new for longer than expected when the run ended.' }),
  'Why the last run is partial: The source’s live feed had published nothing new for longer than expected when the run ended.');
assert.equal(statusReasonLine({ status: 'partial', statusReason: '1 factsheets could not be read; the rest of the run is kept.' }), 'Why the last run is partial: 1 factsheets could not be read; the rest of the run is kept.');
assert.equal(statusReasonLine({ status: 'failed', statusReason: 'The last run did not finish' }), 'Why the last run failed: The last run did not finish.');
assert.equal(statusReasonLine({ status: 'ok', statusReason: 'x' }), null);
assert.equal(statusReasonLine({ status: 'partial', statusReason: null }), null);
assert.equal(statusReasonLine({ status: 'partial' }), null);
assert.equal(lateRuleSentence([{ updateFreq: 'daily', staleAfterHours: 72 }, { updateFreq: 'monthly', staleAfterHours: 960 }, { updateFreq: 'one-off', staleAfterHours: null }]),
  'a daily source after 3 days, a monthly source after 40 days');
assert.equal(lateRuleSentence([{}, { updateFreq: 'daily' }]), null);

// ---- T17: a code never gets the label of another family ----
const audit = cpvName('39225500');
assert.equal(audit?.exact, false, '39225500 is not in the 366-code selection');
assert.equal(cpvOwnName('39225500'), null, 'the card prints no name for it: the division’s title is not the code’s name');
assert.equal(cpvOwnName('35800000'), 'Individual and support equipment');
assert.equal(cpvOwnName('99999999'), null);
const titles = (cpvData as { codes: Record<string, string> }).codes;
for (const [code, title] of Object.entries(titles)) assert.equal(cpvOwnName(code), title, `a code of the selection is named by its own title: ${code}`);
// 50 random codes (a fixed seed): a name is the code's own title, or the title of its own division (or, in division 35, its group); never another family's.
let seed = 52;
const rnd = () => { seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const divisions = Object.keys(titles).filter((c) => c.endsWith('000000')).map((c) => c.slice(0, 2));
const allDivisions = ['03', '09', '14', '15', '16', '18', '19', '22', '24', '30', '31', '32', '33', '34', '35', '37', '38', '39', '42', '43', '44', '45', '48', '50', '51', '55', '60', '63', '64', '65', '66', '70', '71', '72', '73', '75', '77', '79', '80', '85', '90', '92', '98'];
const ownerOf = new Map<string, string>();
for (const d of allDivisions) { const l = cpvDivisionLabel(`${d}000000`); if (l) ownerOf.set(l, d); }
assert.ok(ownerOf.size >= 30 && divisions.length > 0);
const samples: string[] = ['39225500', '39150000', '44316400', '50640000', '79710000', '35310000'];
while (samples.length < 56) samples.push(`${allDivisions[Math.floor(rnd() * allDivisions.length)]}${String(Math.floor(rnd() * 1_000_000)).padStart(6, '0')}`);
for (const code of samples) {
  const n = cpvName(code);
  if (!n) continue;
  if (n.exact) { assert.ok(code in titles || /00000$/.test(code), `exact only for a code we hold: ${code}`); continue; }
  const owner = ownerOf.get(n.label);
  const is35Group = code.startsWith('35') && /^(Emergency|Police|Weapons|Military|Warships|Individual)/.test(n.label);
  assert.ok(owner === code.slice(0, 2) || is35Group, `${code} got the label "${n.label}" of another family`);
  assert.equal(cpvOwnName(code), null, `a non-exact name is not printed beside the code: ${code}`);
}
// The demo card for the warehouse-racking notice (CPV 39150000, not in the selection) prints no name.
const racking = tenderMock.allTenders(REF).find((t) => t.cpv === '39150000');
assert.ok(racking && cpvOwnName(racking.cpv!) === null);

console.log('wp52b.check: ok');
