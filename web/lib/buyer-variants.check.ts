/**
 * Self-check of the buyer-family line (WP-22, 16 October 2026). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { variantsLine, variantsSummary } from './format';

assert.equal(variantsLine(0), null);
assert.equal(variantsLine(1), 'Includes 1 other name variant of this body');
assert.equal(variantsLine(21), 'Includes 21 other name variants of this body');
// WP-175 (D-4, D-6): the buyer page counts the names it can show, and says when the other records carry none of their own
assert.equal(variantsSummary(0, 0), null);
assert.equal(variantsSummary(145, 60), 'Published under 60 other names (145 other records of this body)');
assert.equal(variantsSummary(1, 1), 'Published under one other name (one other record of this body)');
assert.equal(variantsSummary(3, 0), 'Joins 3 other records of this body, all under this name (spelt differently only in case, accents or punctuation)');
console.log('buyer-variants checks passed');
