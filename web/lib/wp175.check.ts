/**
 * Self-check of WP-175 (QA of 24 November 2026, organisations and market data): a company's value share where none of its contracts
 * states a value (D-2), the typical-size line of one contract or of contracts that all state one (D-9, F20), a name's unpaired
 * guillemet and TKMS (F28), and the contract period's month names (D-20). Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { sizeLine, valueShare } from './competition';
import { displayName } from './display-name';
import { spanText } from './contract-period';

// D-2: "EUR 0 of EUR 944,939,271 (0%)" was a share nobody knows
const s = { key: '8051', contracts: 1, total: 39, currency: 'EUR', value: 0, valued: 0, valueTotal: 6_723_103, valuedTotal: 33 };
assert.equal(valueShare(s), 'Not stated: none of its contracts there states a value in EUR (all stated there: EUR 6,723,103 over 33 contracts with a stated value)');
assert.equal(valueShare({ ...s, value: 1_000, valued: 1, valuedTotal: 1, valueTotal: 1_000 }), 'EUR 1,000 of EUR 1,000 (100%), over 1 contract with a stated value');

// D-9, F20
assert.equal(sizeLine({ size: { currency: 'EUR', median: 4_120_000, valued: 1, otherCurrencies: 0 }, withoutValue: 29, contracts: 30 }),
  'EUR 4,120,000, the one contract with a value in EUR. 29 of its 30 contracts state no contract value.');
assert.equal(sizeLine({ size: { currency: 'EUR', median: 153_660, valued: 14, otherCurrencies: 1 }, withoutValue: 0, contracts: 15 }),
  'Median EUR 153,660, over the 14 contracts with a value in EUR; 1 more in another currency. All 15 of its contracts state a contract value.');
assert.equal(sizeLine({ size: null, withoutValue: 1, contracts: 1 }), 'No contract value stated: its one contract states no contract value.');

// F28
assert.equal(displayName('«LEONARDO SpA', 'title'), 'LEONARDO SpA');
assert.equal(displayName('«Leonardo» SpA', 'title'), '«Leonardo» SpA');
assert.equal(displayName('TKMS ATLAS ELEKTRONIK GMBH', 'title'), 'TKMS Atlas Elektronik GmbH');

// D-20: "22 Sep 2026", as every other date of the site, not the locale's "Sept"
assert.equal(spanText({ start: '2026-09-22', end: '2026-11-28', endBasis: 'stated', duration: null, durationUnit: null, renewal: null, renewalsMax: null }),
  '22 Sep 2026 – 28 Nov 2026');
console.log('wp175 ok');
