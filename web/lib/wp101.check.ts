/**
 * Self-check of WP-101 (persona round of 24 October 2026, search): a run of one group's terms is one slot (as the API reads it,
 * backend/dgate/search_terms.py), a notice number opens the tender list on every status, and the product words of the personas
 * (Drehteile, Frästeile, Zerspanung, wiring, harness, cyber, ammunition) find their codes in the CPV picker and the supplier filter.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { CPV_FULL } from './cpv-full';
import { cpvForWords, cpvSearch, productNote } from './cpv';
import { NOTICE_NUMBER, buyerNames, expand, matchesSlots, tenderListQuery } from './search-terms';

// ---------------------------------------------------------------- two words of one group: one slot, either word's notices
const e = expand(['Drehteile', 'Frästeile']);
assert.equal(e.slots.length, 1);
assert.deepEqual(e.slots[0][0], ['Drehteile', 'Frästeile']);
// WP-110: machining is a group of its own (general spare parts came first, p03)
assert.ok(!e.also.includes('Drehteile') && !e.also.includes('Frästeile') && e.also.includes('Zerspanung'), e.also.join(', '));
assert.ok(matchesSlots(e.slots, ['Frästeile für Kettenfahrzeuge'], null));
assert.ok(!matchesSlots(e.slots, ['Ersatzteile Leopard 2'], null));
assert.ok(!matchesSlots(e.slots, ['Reinigung der Kaserne'], null));
assert.equal(expand(['Drehteile', 'Munition']).slots.length, 2);
// WP-110: machining its own group; "SSI" (French fire safety system) no longer cyber (lib/wp110.check.ts)
for (const [q, id] of [['Zerspanung', 'machining'], ['CNC', 'machining'], ['harness', 'wiring'], ['Kabelbaum', 'wiring'], ['Stanzteile', 'stampings'],
  ['Gussteile', 'castings'], ['cyber', 'cyber'], ['cybersécurité', 'cyber'], ['Cybersicherheit', 'cyber'], ['lont', 'ammunition']] as const) {
  assert.deepEqual(expand([q]).groups.map((g) => g.id), [id], q);
}
for (const abbr of ['RBLog', 'AU', 'WOG', 'JW', 'NAVARM', 'TERRARM', 'ARMAEREO']) assert.ok(buyerNames(abbr).length > 0, abbr);

// ---------------------------------------------------------------- a notice number: every status
for (const q of ['220199-2026', '2026/S 203-724451']) assert.ok(NOTICE_NUMBER.test(q), q);
for (const q of ['35613000', 'drone', '2026', '220199-2026 x']) assert.ok(!NOTICE_NUMBER.test(q), q);
// the global search's "see all" of tenders (lib/search.ts seeAllHref) opens the list so
assert.equal(new URLSearchParams(tenderListQuery('220199-2026')).toString(), 'q=220199-2026&status=all');
assert.equal(new URLSearchParams(tenderListQuery('drone')).toString(), 'q=drone');

// ---------------------------------------------------------------- the CPV picker and the supplier product filter
const picked = (q: string) => cpvSearch(q, 20, CPV_FULL).map((c) => c.code);
for (const q of ['Drehteile', 'Frästeile', 'Zerspanung', 'CNC', 'Präzisionsteile']) {
  const got = picked(q);
  assert.ok(got.includes('34320000') && got.includes('35421000'), `${q}: ${got.join(' ')}`);
  assert.ok(productNote(q), q);                                    // says the CPV has no code for machined parts as such
}
assert.ok(picked('wiring').includes('31611000') && picked('Kabelbaum').includes('31612000'));
for (const q of ['cyber', 'cybersecurity', 'cybersécurité', 'security software']) {
  const m = cpvForWords(q);
  assert.equal(m.via, 'keyword', q);
  assert.ok(m.prefixes.some((p) => p.startsWith('4873')) && m.prefixes.some((p) => p.startsWith('72')), `${q}: ${m.prefixes.join(' ')}`);
}
// ammunition: the weapons-and-ammunition group 353 and the explosives 2461, as the tender list's ammunition group (Mesko's 35300000)
const ammo = cpvForWords('ammunition');
assert.ok(ammo.prefixes.includes('353') && ammo.prefixes.includes('2461'), ammo.prefixes.join(' '));
assert.ok(cpvForWords('detonating cord').prefixes.includes('24615'));

console.log('wp101 checks passed');
