/**
 * Self-check of the product search of the supplier map (U9, 18 October 2026): a word is turned into CPV prefixes from the
 * finder's own vocabulary. Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { cpvForWords, cpvPrefix } from './cpv';
import { countryName, cpvDivisionLabel } from './taxonomy';

const ammo = cpvForWords('ammunition');
assert.ok(ammo.matched > 0 && ammo.prefixes.length > 0, 'the finder knows the word');
assert.ok(ammo.prefixes.every((p) => /^\d{2,8}$/.test(p)), 'prefixes are digits');
assert.ok(ammo.prefixes.some((p) => p.startsWith('3533')), 'ammunition is in 3533');
assert.ok(ammo.codes.every((c) => c.title.toLowerCase().includes('ammunition')), 'every code shown holds the word in its title');
// A prefix already covered by a shorter one is dropped: a group and its members count once.
for (const a of ammo.prefixes) for (const b of ammo.prefixes) if (a !== b) assert.ok(!a.startsWith(b), `${a} is covered by ${b}`);
// Every word must be in the title; short words and nothing are no search at all.
assert.deepEqual(cpvForWords('').prefixes, []);
assert.deepEqual(cpvForWords('a an').prefixes, [], 'words under three letters are ignored');
assert.deepEqual(cpvForWords('zzzzqqq').prefixes, [], 'a word the vocabulary lacks matches nothing');
assert.ok(cpvForWords('military vehicles').matched <= cpvForWords('vehicles').matched, 'more words, fewer codes');
// The cap: more prefixes than the API takes are cut, and said to be.
const wide = cpvForWords('military', 2);
assert.ok(wide.prefixes.length <= 2 && wide.truncated, 'cut at the maximum and said so');
assert.equal(cpvPrefix('35330000'), '3533');

// U9: the country names of the supplier table, and the two divisions that had none.
assert.equal(countryName('US'), 'United States');
assert.equal(countryName('IL'), 'Israel');
assert.equal(countryName('DE'), 'Germany', 'a listed name still wins');
assert.equal(countryName('XX'), 'XX', 'a code that is no country stays as it is');
assert.equal(countryName('ZZ'), 'ZZ');
assert.match(cpvDivisionLabel('37') ?? '', /^Musical instruments/);
assert.match(cpvDivisionLabel('92') ?? '', /^Recreational/);
console.log('cpv.check ok');
