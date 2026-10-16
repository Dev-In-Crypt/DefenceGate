/**
 * Self-check of the buyer-family line (WP-22, 16 October 2026). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { variantsLine } from './format';

assert.equal(variantsLine(0), null);
assert.equal(variantsLine(1), 'Includes 1 other name variant of this body');
assert.equal(variantsLine(21), 'Includes 21 other name variants of this body');
console.log('buyer-variants checks passed');
