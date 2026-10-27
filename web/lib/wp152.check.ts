/**
 * Self-check of WP-152: the share and size lines of a company's competitor intelligence (lib/competition.ts). A share of a few per
 * cent is never printed as 0%, a value share is said only where the slice states a value, and the typical size never hides how many
 * contracts state none. Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { classLabel, countShare, sharePercent, sizeLine, valueShare } from './competition';
import { cpvGroupTitle, cpvTitle } from './cpv';

assert.equal(sharePercent(1, 250), '0.4%');
assert.equal(sharePercent(1, 2000), 'under 0.1%');
assert.equal(sharePercent(1, 3), '33%');
assert.equal(sharePercent(0, 7), '0%');
assert.equal(sharePercent(1, 0), '');

const s = { key: '3541', contracts: 2, total: 40, currency: 'EUR', value: 1_000_000, valued: 1, valueTotal: 3_000_000, valuedTotal: 2 };
assert.equal(countShare(s), '2 of 40 (5%)');
assert.equal(valueShare(s), 'EUR 1,000,000 of EUR 3,000,000 (33%), over 2 contracts with a stated value');
assert.equal(valueShare({ ...s, currency: null, value: null, valueTotal: null, valuedTotal: null }), null);

assert.equal(sizeLine({ size: null, withoutValue: 3, contracts: 3 }), 'No contract value stated: 3 of its 3 contracts state no contract value.');
assert.equal(sizeLine({ size: { currency: 'EUR', median: 1_200_000, valued: 4, otherCurrencies: 1 }, withoutValue: 5, contracts: 10 }),
  'Median EUR 1,200,000, over the 4 contracts with a value in EUR; 1 more in another currency. 5 of its 10 contracts state no contract value.');

assert.equal(classLabel('3541', cpvTitle, cpvGroupTitle), '3541 Armoured military vehicles');
assert.equal(classLabel('3542', () => null, (g) => (g === '354' ? 'Military vehicles and associated parts' : null)),
  '3542 (group 354: Military vehicles and associated parts)');
assert.equal(classLabel('9999', () => null, () => null), '9999');
console.log('wp152 ok');
