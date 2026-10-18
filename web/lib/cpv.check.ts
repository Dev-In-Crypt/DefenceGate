/**
 * Self-check of the product search of the supplier map (U9, 18 October 2026): a word is turned into CPV prefixes from the
 * finder's own vocabulary. Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { PRODUCT_KEYWORDS, cpvForWords, cpvPrefix, cpvTitle } from './cpv';
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
// WP-43 (verification 3, finding 9): the curated product words. "drone", "explosives" and "body armour" found nothing, and "tank" found heating tanks.
const drone = cpvForWords('drone');
assert.equal(drone.via, 'keyword');
assert.deepEqual(drone.prefixes, ['35613', '347112'], 'unmanned aerial vehicles, and non-piloted aircraft');
assert.deepEqual(drone.codes.map((c) => c.title), ['Unmanned aerial vehicles', 'Non-piloted aircraft'], 'the matched codes are shown with their official titles');
assert.deepEqual(cpvForWords('Drones').prefixes, drone.prefixes, 'case and plural');
assert.deepEqual(cpvForWords('UAV').prefixes, drone.prefixes);
assert.deepEqual(cpvForWords('explosives').prefixes, ['246']);
assert.deepEqual(cpvForWords('body armour').prefixes, ['35815']);
assert.deepEqual(cpvForWords('Body  Armor').prefixes, ['35815'], 'the American spelling, any spacing');
assert.deepEqual(cpvForWords('bullet-proof').prefixes, ['35815'], 'a hyphen is a space');
assert.deepEqual(cpvForWords('bulletproof').prefixes, ['35815']);
assert.deepEqual(cpvForWords('ammo').prefixes, ['3533']);
const tank = cpvForWords('tank');
assert.deepEqual(tank.prefixes, ['35411'], 'a tank is a battle tank, not a heating tank (44600000)');
assert.ok(!tank.prefixes.some((p) => '44600000'.startsWith(p)));
assert.match(tank.note ?? '', /44600000/, 'and the page says how to reach the other tanks');
assert.deepEqual(cpvForWords('armored vehicles').prefixes, ['3541']);
// The whole query must be listed words; anything else is searched in the finder's titles as before.
assert.equal(cpvForWords('drone zzzz').via, 'title');
assert.deepEqual(cpvForWords('drone zzzz').prefixes, []);
assert.equal(cpvForWords('ammunition').via, 'title', 'a word the finder knows keeps the finder');
assert.deepEqual(cpvForWords('drone tank').prefixes, ['35411', '35613', '347112'], 'two listed words give both');
// The list itself: official codes, titles that agree with the finder's where it holds the code, and no word in two entries.
const seen = new Map<string, number>();
PRODUCT_KEYWORDS.forEach((e, i) => {
  assert.ok(e.codes.length > 0 && e.words.length > 0);
  for (const c of e.codes) {
    assert.match(c.code, /^\d{8}$/, `${c.code} is an 8-digit CPV code`);
    assert.ok(c.title.length > 0);
    const own = cpvTitle(c.code);
    if (own) assert.equal(c.title, own, `${c.code}: the title is the vocabulary's`);
  }
  for (const w of e.words) {
    const key = w.toLowerCase();
    assert.ok(!seen.has(key) || seen.get(key) === i, `"${w}" is listed under two entries`);
    seen.set(key, i);
    assert.equal(key, w, 'words are written in lower case');
  }
});
assert.ok(PRODUCT_KEYWORDS.length >= 8 && PRODUCT_KEYWORDS.length <= 30, 'a small list, not a thesaurus');
console.log('cpv.check ok');
