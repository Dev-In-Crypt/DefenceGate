/**
 * Self-check of a buyer page's unit choice (WP-144, 26 October 2026). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { chosenUnit, unitKey, unitOptions } from './buyer-units';
import type { BuyerUnit } from './types';

const units: BuyerUnit[] = [
  { key: 'politechnika warszawska', name: 'POLITECHNIKA WARSZAWSKA', tenderCount: 5, coreCount: 5 },
  { key: 'politechnika warszawska wydzial transportu', name: 'Politechnika Warszawska, Wydział Transportu', tenderCount: 1234, coreCount: 2 },
];

// the API's folding: case, accents (and the Polish ł), punctuation and runs of spaces
assert.equal(unitKey('Politechnika Warszawska, Wydział  Transportu'), 'politechnika warszawska wydzial transportu');
assert.equal(unitKey(' Ministère des Armées - DGA/DO '), 'ministere des armees dga do');

// the address names a unit by its key, or by its name as stated
assert.equal(chosenUnit(units, 'politechnika warszawska wydzial transportu'), units[1]);
assert.equal(chosenUnit(units, 'Politechnika Warszawska, Wydział Transportu'), units[1]);
assert.equal(chosenUnit(units, ['politechnika warszawska', 'x']), units[0]);
// nothing, an unknown unit, or a buyer of one unit: all units
assert.equal(chosenUnit(units, undefined), null);
assert.equal(chosenUnit(units, '  '), null);
assert.equal(chosenUnit(units, 'wydzial fizyki'), null);
assert.equal(chosenUnit(units.slice(0, 1), 'politechnika warszawska'), null);
assert.equal(chosenUnit(undefined, 'politechnika warszawska'), null);

// each option says its tenders; the value is the key the API reads
assert.deepEqual(unitOptions(units).map((o) => o.value), units.map((u) => u.key));
assert.match(unitOptions(units)[1].label, /\(1,234\)$/);
assert.doesNotMatch(unitOptions(units)[0].label, /POLITECHNIKA/);   // an all-caps name is shown in title case
console.log('buyer-units checks passed');
