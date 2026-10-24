/**
 * WP-113 (coverage audit of 24 October 2026: source field mappings), without a browser:
 * npx tsc lib/wp113.check.ts --outDir /tmp/chk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule
 * && node /tmp/chk/wp113.check.js
 */
import assert from 'node:assert/strict';
import { legalBasisLabel, procedureLabel } from './taxonomy';

// TED's pre-eForms "other" legal basis, as old notices spell it, is said like the eForms one
assert.equal(legalBasisLabel('CODE_OTHERS'), legalBasisLabel('other'));
assert.ok(legalBasisLabel('CODE_OTHERS'));
// PLACSP code 7, named by the mapper in Spanish, in English
assert.equal(procedureLabel('Derivado de acuerdo marco'), 'Contract based on a framework agreement');
// the API's English words for TED's legacy codes need no second translation
assert.equal(procedureLabel('Negotiated procedure'), null);
console.log('wp113 checks passed');
