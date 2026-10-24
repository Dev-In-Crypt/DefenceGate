/**
 * Self-check of WP-98 (persona round of 23 October 2026, section C, items 1 to 4): the keyword map of other languages and the
 * buyers' abbreviations (lib/data/search-terms.json, the API's copy held identical by backend/tests/unit/test_wp98.py), read by the
 * demo data as the API reads them: every word in any order, a group's terms in other languages, the "also searched" line.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { CPV_FULL } from './cpv-full';
import { queryBuyers, queryTenders } from './mock/tenders';
import { SEARCH_GROUPS, alsoSearchedLine, buyerNames, expand, foldWords, matchesSlots } from './search-terms';

// ---------------------------------------------------------------- the map: codes of the vocabulary, no term twice
for (const g of SEARCH_GROUPS) {
  for (const p of g.cpv) assert.ok([...CPV_FULL.keys()].some((c) => c.startsWith(p)), `${g.id}: ${p}`);
  const keys = g.terms.map((t) => foldWords(t).join(' '));
  assert.equal(new Set(keys).size, keys.length, `${g.id}: a term twice`);
}
assert.deepEqual(foldWords('Materiały wybuchowe, Frästeile'), ['materialy', 'wybuchowe', 'frasteile']);

// ---------------------------------------------------------------- a word of each language is read as its group
const groupOf = (q: string) => expand(q.split(/\s+/)).groups.map((g) => g.id);
for (const [q, id] of [
  ['fardamento', 'uniforms'], ['botas', 'uniforms'], ['vêtements', 'uniforms'], ['Bekleidung', 'uniforms'], ['odzież', 'uniforms'], ['kleding', 'uniforms'],
  ['Ersatzteile', 'spare-parts'], ['Drehteile', 'spare-parts'], ['recambios', 'spare-parts'], ['części zamienne', 'spare-parts'], ['spare parts', 'spare-parts'],
  ['Drohnen', 'drones'], ['drony', 'drones'], ['UAV', 'drones'], ['brandstof', 'fuel'], ['paliwo', 'fuel'], ['logistiek', 'logistics'],
  ['amunicja', 'ammunition'], ['materiały wybuchowe', 'ammunition'], ['Sprengstoff', 'ammunition'], ['night vision', 'night-vision'], ['body armour', 'body-armour'],
] as const) assert.deepEqual(groupOf(q), [id], q);
assert.deepEqual(groupOf('Drohnendetektoren'), []);

// ---------------------------------------------------------------- every word, in any order; a group's terms in the titles
const slots = (q: string) => expand(q.split(/\s+/)).slots;
assert.ok(matchesSlots(slots('parts spare'), ['Spare parts for the Boxer'], null));
assert.ok(matchesSlots(slots('spare parts'), ['Lieferung Ersatzteile'], null));
assert.ok(!matchesSlots(slots('spare parts'), ['Spare tyres'], null));
assert.ok(matchesSlots(slots('fardamento'), ['Combat uniforms'], null));
assert.ok(!matchesSlots(slots('fardamento'), ['Supply'], 'Uniform Buyer Agency'), 'a term of a group reads the titles, not the buyer');
assert.ok(matchesSlots(slots('counter drone'), ['Counter-UAV systems'], null));

// ---------------------------------------------------------------- the demo lists read them so
const found = (q: string, status: 'open' | 'all' = 'all') => queryTenders({ q, status }).items.map((t) => t.title);
assert.ok(found('fardamento').includes('Uniform textiles framework'));
assert.ok(found('Ersatzteile').includes('Prior information: vehicle spare parts framework for 2027'));
assert.ok(found('parts spare').includes('Prior information: vehicle spare parts framework for 2027'));
assert.ok(found('brandstof').includes('Fuel supply framework'));
assert.ok(found('Logistik').includes('Packaging and logistics services'));
const page = queryTenders({ q: 'fardamento', status: 'all' });
assert.equal(page.searchGroups?.[0]?.id, 'uniforms');
assert.ok(page.alsoSearched?.includes('Bekleidung'));
assert.deepEqual(queryTenders({ q: 'housings' }).alsoSearched, []);

// ---------------------------------------------------------------- the line, and the abbreviations
assert.equal(alsoSearchedLine([]), null);
assert.equal(alsoSearchedLine(['Drohne', 'UAV']), 'Also searched, the same product in other languages: Drohne, UAV.');
assert.match(alsoSearchedLine(Array.from({ length: 10 }, (_, i) => `t${i}`)) ?? '', /t7 and 2 more\.$/);
for (const a of ['BAAINBw', 'DMO', 'DGA', 'JAE MALE', 'jaemale']) assert.ok(buyerNames(a).length > 0, a);
assert.deepEqual(buyerNames('DMOS'), []);
assert.equal(queryBuyers({ q: 'Demo Defence Materiel Organisation' }).items[0]?.country, 'NL');

console.log('wp98 checks passed');
