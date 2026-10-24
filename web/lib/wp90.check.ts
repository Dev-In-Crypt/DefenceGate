/**
 * Self-check of WP-90 (UX audit of 22 October 2026, section 5: the analyst path, persona Jonas, a German defence-electronics analyst).
 *   1. "Subscribe to this search": the calendar and the feed carry exactly the list's filters; a closed list has no calendar
 *   2. the search reads the English titles of a notice's CPV codes (the demo data reads them as the API does)
 *   3. CPV presets of official codes, main code only, excluded codes, 10/25/50 per page, deadline presets
 *   7. the change list by kind of change; the week under way
 *   the calendar file names the tenders it leaves out (no silent cut)
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import {
  CPV_PRESETS, DEADLINE_PRESETS, activeDeadlinePreset, activePreset, deadlineWindow, presetPrefixes, subscription,
} from './analyst';
import { CPV_FULL, cpvTitleHasWord } from './cpv-full';
import { weekMonday, weekOf, weekSoFarLabel } from './digest';
import { CALENDAR_PARAMS, CHANGE_PARAMS, ignoredFilters, parseChangeFilters, parseTenderFilters, toChangeQuery, toTenderQuery } from './filters';
import { buildIcs } from './ics';
import { queryChanges, queryTenders } from './mock/tenders';

// ---------------------------------------------------------------- 3. presets: official codes, read as the CPV filter
const TITLES: Record<string, string> = {
  '35700000': 'Military electronic systems', '35722000': 'Radar', '35723000': 'Air defence radar', '38115000': 'Radar apparatus',
  '38113000': 'Sonars', '35710000': 'Command, control, communication and computer systems', '35400000': 'Military vehicles and associated parts',
  '34100000': 'Motor vehicles', '34300000': 'Parts and accessories for vehicles and their engines', '35300000': 'Weapons, ammunition and associated parts',
  '35810000': 'Individual equipment', '18100000': 'Occupational clothing, special workwear and accessories',
};
// WP-98b widened the uniforms and ammunition presets and added parts and the services (lib/wp98b.check.ts holds those)
assert.deepEqual(CPV_PRESETS.slice(0, 4).map((p) => p.label), ['Military electronics', 'Radar and sonar', 'Communications', 'Vehicles and parts']);
for (const p of CPV_PRESETS) {
  for (const code of p.codes) {
    assert.ok(CPV_FULL.has(code), `${p.id}: ${code} is a code of the vocabulary`);
    if (TITLES[code]) assert.equal(CPV_FULL.get(code), TITLES[code], code);
  }
  assert.equal(activePreset(presetPrefixes(p))?.id, p.id);
  assert.equal(activePreset([...presetPrefixes(p)].reverse())?.id, p.id, 'any order');
}
assert.match(CPV_FULL.get('32000000') ?? '', /communication/i);
assert.deepEqual(presetPrefixes(CPV_PRESETS[0]), ['357']);
assert.deepEqual(presetPrefixes(CPV_PRESETS[1]), ['35722', '35723', '38115', '38113']);
assert.equal(activePreset(['357', '35']), null);
assert.equal(activePreset(undefined), null);

// ---------------------------------------------------------------- 3. deadline presets: from today, both days included
const ref = new Date('2026-10-12T08:00:00Z');
assert.deepEqual(DEADLINE_PRESETS, [7, 14, 30]);
assert.deepEqual(deadlineWindow(7, ref), { deadlineFrom: '2026-10-12', deadlineTo: '2026-10-19' });
assert.equal(activeDeadlinePreset(deadlineWindow(30, ref), ref), 30);
assert.equal(activeDeadlinePreset({ deadlineFrom: '2026-10-12', deadlineTo: '2026-10-20' }, ref), null);

// ---------------------------------------------------------------- 3. main code only, excluded codes, page size: read from the address
const f = parseTenderFilters({ cpv: '357', cpvMain: 'true', notCpv: '3511,35110000-1', size: '25', country: 'de' });
assert.equal(f.cpvMain, true);
assert.deepEqual(f.notCpv, ['3511', '35110000']);
assert.equal(f.pageSize, 25);
assert.equal(toTenderQuery(f), '?country=DE&cpv=357&cpvMain=true&notCpv=3511%2C35110000&size=25');
assert.deepEqual(parseTenderFilters(Object.fromEntries(new URLSearchParams(toTenderQuery(f)))), f, 'the address reads back the same');
assert.equal(parseTenderFilters({ cpvMain: 'true' }).cpvMain, undefined, 'main code only is read with a code only');
assert.equal(parseTenderFilters({ size: '100' }).pageSize, 10);
assert.equal(toTenderQuery({ pageSize: 100 }), '', 'a size set by code (the buyer page) is not an address size');
assert.deepEqual(ignoredFilters({ notCpv: 'x1', size: '100', cpvMain: 'yes' }, 'tenders'), [
  'Ignored filter: notCpv=x1 (CPV codes are 2 to 8 digits)', 'Ignored filter: cpvMain=yes (use true)', 'Ignored filter: size=100 (use 10, 25, 50)']);
assert.ok(CALENDAR_PARAMS.includes('notCpv') && CALENDAR_PARAMS.includes('cpvMain') && !(CALENDAR_PARAMS as readonly string[]).includes('size'));

// ---------------------------------------------------------------- 1. subscribe to this search: exactly its filters
const search = parseTenderFilters({ q: 'radar', country: 'DE,PL', cpv: '357', cpvMain: 'true', notCpv: '3511', scope: 'core', from: '2026-10-12', to: '2026-11-12', size: '50', sort: 'published-desc', page: '3' });
const s = subscription(search, 'https://defencegatehub.com/');
assert.equal(s.ics, '/calendar.ics?kind=tenders&country=DE%2CPL&q=radar&scope=core&cpv=357&cpvMain=true&notCpv=3511&from=2026-10-12&to=2026-11-12');
assert.equal(s.webcal, `webcal://defencegatehub.com${s.ics}`);
assert.equal(s.atom, '/changes.atom?country=DE%2CPL&scope=core&q=radar&cpv=357&cpvMain=true&notCpv=3511&status=open&from=2026-10-12&to=2026-11-12');
// every parameter of the two is one the feed reads (else the feed answers 422), and the list's sort, page and size are not in them
for (const [href, known] of [[s.ics!, CALENDAR_PARAMS], [s.atom, CHANGE_PARAMS]] as const) {
  for (const k of new URLSearchParams(href.split('?')[1]).keys()) assert.ok((known as readonly string[]).includes(k), `${href}: ${k}`);
  assert.doesNotMatch(href, /sort=|page=|size=/);
}
// the feed reads back the search's filters
const back = parseChangeFilters(Object.fromEntries(new URLSearchParams(s.atom.split('?')[1])));
assert.deepEqual([back.q, back.cpv, back.cpvMain, back.notCpv, back.status, back.scope, back.country], ['radar', ['357'], true, ['3511'], 'open', 'core', ['DE', 'PL']]);
assert.equal(subscription({ status: 'closed' }, 'https://x.test').ics, null, 'a calendar holds open tenders only');
assert.equal(subscription({ status: 'all' }, 'https://x.test').ics, '/calendar.ics?kind=tenders');
assert.equal(subscription({}, 'https://x.test').atom, '/changes.atom?status=open');
// the change list reads a status only when it is asked for (its own default is every status)
assert.equal(parseChangeFilters({}).status, undefined);
assert.equal(toChangeQuery(parseChangeFilters({ status: 'closed', kind: 'deadline' })), '?status=closed&kind=deadline');
assert.deepEqual(ignoredFilters({ kind: 'deadline', status: 'soon' }, 'changes'), ['Ignored filter: status=soon (use open, closed, planned, all)']);

// ---------------------------------------------------------------- 2. the search reads the English titles of the codes
assert.ok(cpvTitleHasWord('35722000', 'Radar'));
assert.ok(cpvTitleHasWord('38113000', 'sonars'));
assert.ok(!cpvTitleHasWord('35722000', 'ada'), 'the beginning of a word only');
assert.ok(!cpvTitleHasWord('35722000', 'ra'), 'three letters at least');
const byCode = queryTenders({ q: 'individual', status: 'all', scope: 'all', pageSize: 100 }, ref).items.map((t) => t.noticeId);
assert.deepEqual(byCode, ['561204-2026'], 'a notice under 35800000 Individual and support equipment, whose title does not say it');

// ---------------------------------------------------------------- 3. the demo list reads main code only and excluded codes
const main = (cpvMain: boolean) => queryTenders({ cpv: ['358'], cpvMain, status: 'all', scope: 'all', pageSize: 100 }, ref).items.length;
assert.equal(main(false), 1);
assert.equal(main(true), 0, 'its main code is 44316400');
const all = queryTenders({ status: 'all', scope: 'all', pageSize: 100 }, ref).total;
assert.equal(queryTenders({ notCpv: ['443'], status: 'all', scope: 'all', pageSize: 100 }, ref).total, all - 1);

// ---------------------------------------------------------------- 7. kinds of change, the week under way
const kinds = (kind: 'deadline' | 'value' | 'status' | 'new' | 'amended') => queryChanges({ kind, scope: 'all', pageSize: 100 }, ref).items;
assert.ok(kinds('deadline').length > 0 && kinds('deadline').every((c) => c.changes.some((l) => l.field === 'deadline')));
assert.ok(kinds('value').every((c) => c.changes.some((l) => l.field === 'estimated_value')));
const amendedIds = new Set(kinds('amended').map((c) => c.id));
assert.ok([...kinds('deadline'), ...kinds('value')].every((c) => amendedIds.has(c.id)), 'each kind is a part of the amendments');
assert.deepEqual(kinds('value').map((c) => c.tender.noticeId), ['561204-2026']);
assert.equal(weekOf(ref), '2026-W42');
assert.equal(weekOf(new Date('2026-01-01T12:00:00Z')), '2026-W01');
assert.equal(weekOf(new Date('2027-01-01T12:00:00Z')), '2026-W53');
assert.equal(weekOf(new Date('2024-12-30T00:00:00Z')), '2025-W01');
assert.equal(weekMonday(weekOf(new Date('2026-10-23T09:00:00Z'))).toISOString(), '2026-10-19T00:00:00.000Z');
assert.equal(weekSoFarLabel('2026-W43', new Date('2026-10-23T09:00:00Z')), 'This week so far: 19 to 23 October 2026');
const thisWeek = queryChanges({ week: weekOf(ref) }, ref);
assert.ok(new Date(thisWeek.windowTo).getTime() <= ref.getTime() + 1, 'the week under way ends now');

// ---------------------------------------------------------------- the calendar file names what it leaves out
const ics = buildIcs([], ref, { longRunning: 3 }).replace(/\r\n /g, '');
assert.match(ics, /3 open tenders have a deadline more than three years ahead/);
assert.doesNotMatch(buildIcs([], ref), /three years ahead/);

console.log('wp90 checks ok');
