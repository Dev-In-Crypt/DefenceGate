/**
 * Self-check of WP-105 (persona round of 24 October 2026: the supplier report, the buyer pages, the market's money).
 *   1. the demand request: seven countries, the company's own country when it is one of them, nothing else
 *   2. the code sets: automotive with 35400000; one machining list for the profile and the tender list; textiles, naval, aviation
 *   3. the words under the lists: no "names them all", no "the list stops at 30" for the new rule
 *   4. the national routes: the Netherlands' and Italy's export authority for military goods from the official pages; no other
 *      country's authority named to a Portuguese or French company
 *   5. the answers kept in the tab, so the report after the results page asks the API nothing
 *   6. the money in words
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CPV_PRESETS, activePreset, presetPrefixes } from './analyst';
import { ANSWER_SECONDS, recall, remember } from './answer-cache';
import { AUTOMOTIVE_SET, AVIATION_SET, CODE_SETS, MACHINING_SET, NAVAL_SET, UNIFORM_SET, cpvPrefix } from './cpv';
import { CPV_FULL } from './cpv-full';
import { countryRoute } from './country-routes';
import { DEMAND_COUNTRIES, SAMPLE_CPV, approachOthersLine, demandRequest, otherWinnersLine, type DemandCountry } from './demand';
import { moneyLine, valuedShare } from './market-money';
import { parseProfile } from './profile';

// ---------------------------------------------------------------- 1. the request
assert.deepEqual([...DEMAND_COUNTRIES], ['ES', 'DE', 'FR', 'PL', 'NL', 'PT', 'IT']);
const base = parseProfile(JSON.parse(readFileSync('e2e/fixtures/profile-es-sup-civil.json', 'utf8')));
assert.equal(demandRequest({ ...base, country: 'PT' })?.home, 'PT', 'a Portuguese company is a map country now');
assert.equal(demandRequest({ ...base, country: 'IT' })?.home, 'IT');
assert.equal(demandRequest({ ...base, country: 'BE' })?.home, undefined, 'a country outside the map is not sent');
assert.deepEqual(Object.keys(demandRequest({ ...base, country: 'DE' }) ?? {}), ['cpv', 'countries', 'home']);

// ---------------------------------------------------------------- 2. the code sets
assert.ok(AUTOMOTIVE_SET.includes('35400000' as never), 'p01: military vehicles and associated parts');
assert.ok(!AUTOMOTIVE_SET.some((c) => c !== '35400000' && c.startsWith('354')), 'no code that 35400000 already covers');
assert.deepEqual([...SAMPLE_CPV], [...AUTOMOTIVE_SET], 'the landing counts the report\'s automotive codes');
const preset = (id: string) => CPV_PRESETS.find((p) => p.id === id)!;
const set = (key: string) => CODE_SETS.find((s) => s.key === key)!;
// p03: the profile's machining button and the tender list's group are one list, so "Open now" counts the same
assert.deepEqual([...set('machining').codes], [...preset('parts').codes]);
assert.deepEqual(set('machining').codes, MACHINING_SET);
// p02: the textile button is the tender list's uniforms group
assert.deepEqual([...set('uniforms').codes], [...preset('uniforms').codes]);
assert.deepEqual(presetPrefixes(preset('uniforms')), ['3581', '181', '182', '183', '188', '351134', '395']);
// p07: naval and aviation, on both
assert.deepEqual([...set('naval').codes], [...NAVAL_SET]);
assert.deepEqual([...preset('naval').codes], [...NAVAL_SET]);
assert.deepEqual([...set('aviation').codes], [...AVIATION_SET]);
assert.deepEqual(presetPrefixes(preset('aviation')), ['347', '356', '5065', '50211']);
assert.equal(CPV_FULL.get('35500000'), 'Warships and associated parts');
assert.equal(CPV_FULL.get('35600000'), 'Military aircrafts, missiles and spacecrafts');
for (const s of CODE_SETS) {
  assert.ok(s.codes.length <= 15, `${s.key}: fits a profile`);
  for (const c of s.codes) assert.ok(CPV_FULL.has(c), `${s.key}: ${c} is an official code`);
}
for (const p of CPV_PRESETS) assert.equal(activePreset(presetPrefixes(p))?.id, p.id, `${p.id}: one preset per set of prefixes`);
assert.equal(new Set(UNIFORM_SET.map(cpvPrefix)).size, UNIFORM_SET.length);

// ---------------------------------------------------------------- 3. the words under the lists
const country = { otherWinners: { winners: 175, awards: 329 } } as unknown as DemandCountry;
const per = otherWinnersLine(country, 1) ?? '';
assert.doesNotMatch(per, /names them all/, 'p01, p04: the report does not name them all under Who to approach');
assert.match(per, /on the list of all winners/);
const more = approachOthersLine({ winners: [], below: { winners: 0, awards: 0 }, more: { winners: 219, awards: 329 } }, 1) ?? '';
assert.doesNotMatch(more, /stops at 30/, 'p01: "37 are named below" then "the list stops at 30"');
assert.match(more, /^219 more winners \(329 awards\) are not listed here: the list names the 30 with the most contracts, every prime/);

// ---------------------------------------------------------------- 4. the national routes
const nl = countryRoute('NL');
assert.match(nl.find((l) => l.key === 'nl-export')!.text, /CDIU\) of Dutch Customs, which reviews the application on behalf of the Ministry of Foreign Affairs/);
assert.ok(nl.find((l) => l.key === 'nl-export')!.link!.url.startsWith('https://www.rijksoverheid.nl/'));
const it = countryRoute('IT');
assert.match(it.find((l) => l.key === 'it-export')!.text, /UAMA\) of the Ministry of Foreign Affairs .+ \(Law 185\/1990, article 7-bis\)/);
for (const c of ['PT', 'FR']) {
  const lines = countryRoute(c);
  const exp = lines.find((l) => l.key === 'export')!;
  assert.ok(exp.open && /^Not covered yet for /.test(exp.text), `${c}: the export authority is not covered, said so`);
  assert.doesNotMatch(lines.map((l) => l.text).join(' '), /BAFA|Secretar[ií]a de Estado|CDIU|UAMA/, `${c}: no other country's authority`);
}
const seed = readFileSync('../backend/seeds/requirements.json', 'utf8');
assert.doesNotMatch(seed, /Spain: Secretaría de Estado de Comercio; Germany: BAFA/, 'p06: the dual-use rule names no country\'s authority to every company');
assert.ok(seed.includes('"requirement": "REQ-EXPORT", "country": "NL"') && seed.includes('"requirement": "REQ-EXPORT", "country": "IT"'));

// ---------------------------------------------------------------- 5. the answers kept in the tab
const mem = new Map<string, string>();
const store = { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => { mem.set(k, v); }, removeItem: (k: string) => { mem.delete(k); } };
remember('demand', '{"cpv":["1"]}', { total: 1 }, 1000, store);
assert.deepEqual(recall('demand', '{"cpv":["1"]}', 2000, store), { total: 1 }, 'the report reads the results page\'s answer');
assert.equal(recall('demand', '{"cpv":["2"]}', 2000, store), null, 'another request is asked');
assert.equal(recall('assess', '{"cpv":["1"]}', 2000, store), null, 'another kind is asked');
assert.equal(recall('demand', '{"cpv":["1"]}', 1000 + ANSWER_SECONDS * 1000 + 1, store), null, 'too old: asked again');
remember('demand', 'a', 1, 0, store);
remember('demand', 'b', 2, 0, store);
assert.equal(recall('demand', 'a', 0, store), null, 'one answer per kind is kept');
assert.equal(recall('demand', 'b', 0, store), 2);
assert.equal(recall('demand', 'b', 0, null), null, 'no storage: nothing kept, nothing breaks');

// ---------------------------------------------------------------- 6. the money in words
assert.equal(moneyLine([{ currency: 'EUR', amount: 1_200_000.4, count: 3, lotEstimates: 0 }, { currency: 'PLN', amount: 40_000, count: 1, lotEstimates: 0 }]),
  'EUR 1,200,000 over 3 contracts; PLN 40,000 over 1 contract');
assert.equal(moneyLine([]), null);
assert.equal(valuedShare(25, 7), '18 of 25 state a contract value');

console.log('wp105 ok');
