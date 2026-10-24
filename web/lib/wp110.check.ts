/**
 * Self-check of WP-110 (round-4 re-check of 24 October 2026, search precision and stability).
 *   1. the product groups: "wiring harness" is one phrase of its group, "wiring" alone (any cabling) and "SSI" (fire safety) are no
 *      group term, machining is a group of its own; a product word never reads the buyer's name (demo search, as the API)
 *   2. the CPV finder's search reads the full vocabulary with the product words: harness, wiring, stamping find codes
 *   3. "Did you mean CPV 31611000 Wiring sets?" in the demo answer
 *   4. a profile saved with an earlier version of a code set is offered the current one, its other codes untouched
 *   5. a services preset reads the main code only; every code a set holds has its title without the full list
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { CPV_PRESETS, presetMainOnly } from './analyst';
import { AUTOMOTIVE_SET, CODE_SETS, MACHINING_SET, PREVIOUS_SETS, cpvDictionaryTitle, cpvSearch, setUpdate } from './cpv';
import { CPV_FULL } from './cpv-full';
import { queryTenders } from './mock/tenders';
import { expand, matchesSlots } from './search-terms';

// ---------------------------------------------------------------- 1. the groups
const ids = (q: string) => expand(q.split(' ')).groups.map((g) => g.id);
assert.deepEqual(ids('wiring harness'), ['wiring']);
assert.equal(expand(['wiring', 'harness']).slots.length, 1, 'one slot: the phrase');
assert.deepEqual(ids('wiring'), [], 'wiring alone is any cabling: a word of its own');
assert.deepEqual(ids('SSI'), [], 'SSI is a French fire safety system, not cyber');
assert.deepEqual(ids('Zerspanung'), ['machining']);
assert.deepEqual(ids('Ersatzteile'), ['spare-parts']);
assert.ok(!expand(['Zerspanung']).slots[0].some((a) => a.join(' ') === 'Ersatzteile'), 'machining is not spare parts');
const cyber = expand(['cyber']).slots;
assert.equal(matchesSlots(cyber, ['Dostawa sprzętu'], 'Centrum Operacji Cybernetycznych'), false, 'a product word never reads the buyer');
assert.equal(matchesSlots(cyber, ['Cybersecurity audit'], 'Ministry'), true);
assert.equal(matchesSlots(expand(['Bundeswehr']).slots, ['Lieferung'], 'Bundeswehr Dienstleistungszentrum'), true, 'a word of no group still does');

// ---------------------------------------------------------------- 2. the finder over the full vocabulary
for (const q of ['harness', 'wiring', 'stamping', 'wiring harness']) {
  assert.ok(cpvSearch(q, 60, CPV_FULL).length > 0, q);
}
assert.equal(cpvSearch('harness', 60, CPV_FULL)[0].code, '31611000', 'the curated words first: Wiring sets');
assert.ok(cpvSearch('3161', 60, CPV_FULL).some((c) => c.code === '31612000'));

// ---------------------------------------------------------------- 3. the hints of the demo answer
const hinted = queryTenders({ q: 'wiring harness', pageSize: 5 });
assert.equal(hinted.cpvHints?.[0]?.code, '31611000');
assert.equal(hinted.cpvHints?.[0]?.title, 'Wiring sets');
assert.equal(hinted.cpvHints?.[0]?.prefix, '31611');
assert.deepEqual(queryTenders({ q: 'Bundeswehr', pageSize: 5 }).cpvHints, []);

// ---------------------------------------------------------------- 4. an earlier version of a set
const oldAuto = PREVIOUS_SETS.automotive![0];
const mine = [...oldAuto, '44531000'];                    // the old set and one code of the visitor's own
const up = setUpdate(mine, 15)!;
assert.equal(up.set.key, 'automotive');
assert.deepEqual(up.add, ['35400000']);
assert.deepEqual(up.remove, ['35420000', '35421000']);
assert.ok(up.codes.includes('44531000'), 'the visitor\'s own code stays');
assert.ok(AUTOMOTIVE_SET.every((c) => up.codes.includes(c)));
assert.equal(setUpdate(up.codes, 15), null, 'up to date: nothing to offer');
assert.equal(setUpdate([...AUTOMOTIVE_SET], 15), null);
assert.equal(setUpdate(['34300000', '35420000'], 15), null, 'a part of an old set is the visitor\'s own choice');
// a code another set holds whole stays: 35421000 is also a machining code
const both = setUpdate([...oldAuto, ...MACHINING_SET.filter((c) => !oldAuto.includes(c))], 15);
assert.ok(both && both.codes.includes('35421000') && !both.remove.includes('35421000'));
assert.ok(both!.codes.length <= 15);

// ---------------------------------------------------------------- 5. presets and titles
assert.equal(presetMainOnly(CPV_PRESETS.find((p) => p.id === 'vehicle-repair')!), true);
assert.equal(presetMainOnly(CPV_PRESETS.find((p) => p.id === 'vehicles')!), false);
for (const s of CODE_SETS) for (const c of s.codes) assert.ok(cpvDictionaryTitle(c), `${s.key} ${c} has a title`);
assert.equal(cpvDictionaryTitle('34322000'), 'Brakes and brake parts');
for (const c of CODE_SETS.flatMap((s) => s.codes)) assert.equal(cpvDictionaryTitle(c), CPV_FULL.get(c), `${c}: the official title`);

console.log('wp110 checks passed');
