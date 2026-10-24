/**
 * Self-check of WP-104 (persona round of 24 October 2026, entities): display names of abbreviations and of a Spanish state
 * company, and the total of a curated company group.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { displayName } from './display-name';
import { querySuppliers } from './mock/suppliers';
import { groupValueLine } from './value-totals';

// ---------------------------------------------------------------- display names
assert.equal(displayName('DID SDS', 'title'), 'DID SDS');                          // was "Did Sds"
assert.equal(displayName('NAVANTIA SA, SME', 'title'), 'Navantia SA, SME');        // was "Navantia SA, Sme"
assert.equal(displayName('NAVANTIA S.A., S.M.E.', 'title'), 'Navantia S.A., S.M.E.');
assert.equal(displayName('MINISTERIO DE DEFENSA', 'title'), 'Ministerio de Defensa');   // a shouted name is still cased
assert.equal(displayName('LOT 1 AND 2'), 'Lot 1 and 2');                           // titles are not names: cased as before
assert.equal(displayName('SAAB AB', 'title'), 'SAAB AB');

// ---------------------------------------------------------------- group totals
assert.equal(groupValueLine(null), null);
assert.equal(groupValueLine(undefined), null);
assert.match(groupValueLine([]) ?? '', /no company of the group states a contract value/);
const line = groupValueLine([{ currency: 'EUR', amount: 326_909_734.4, count: 7, lotEstimates: 0 },
  { currency: 'SEK', amount: 1_000_000, count: 1, lotEstimates: 0 }]) ?? '';
assert.match(line, /^Group total of contract values: EUR 326,909,734 over 7 contracts; SEK 1,000,000 over 1 contract /);
assert.match(line, /never converted/);
const demo = querySuppliers({ group: 'demo' });
assert.deepEqual(demo.groupTotals?.map((t) => [t.currency, t.amount, t.count]), [['EUR', 17_050_000, 7], ['PLN', 7_000_000, 2]]);
assert.equal(querySuppliers({}).groupTotals, null);

console.log('wp104 checks passed');
