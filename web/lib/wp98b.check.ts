/**
 * Self-check of WP-98b (persona round of 23 October 2026, section C items 5 to 7).
 *   5. the CPV presets (goods and services), every code of the official vocabulary; the filters as chips
 *   6. the buyer list's order by the codes; the supplier list's value orders, TED view and value line
 *   7. one coverage constant, held to the tender sources of backend/migrations; its line per country
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { CPV_PRESETS, PRESET_GROUPS, activePreset, filterChips, presetPrefixes } from './analyst';
import { NATIONAL_COVERAGE, coverageLine, coverageLines } from './coverage-copy';
import { CPV_FULL } from './cpv-full';
import { defaultBuyerSort, ignoredFilters, parseBuyerFilters, parseTenderFilters, toBuyerQuery } from './filters';
import { queryBuyers } from './mock/tenders';
import { querySuppliers } from './mock/suppliers';
import { listValueLine } from './value-totals';

// ---------------------------------------------------------------- 5. presets
const ids = CPV_PRESETS.map((p) => p.id);
assert.equal(new Set(ids).size, ids.length, 'one id each');
for (const p of CPV_PRESETS) {
  assert.ok(PRESET_GROUPS.some((g) => g.id === p.group), `${p.id}: a group`);
  for (const c of p.codes) assert.ok(CPV_FULL.has(c), `${p.id}: ${c} is a code of the CPV 2008 vocabulary`);
  assert.ok(presetPrefixes(p).length <= 20, 'the CPV filter takes 20 prefixes');
  assert.equal(activePreset([...presetPrefixes(p)].reverse())?.id, p.id);
}
const preset = (id: string) => CPV_PRESETS.find((p) => p.id === id)!;
// p02: footwear, garments, outerwear, textiles and protective clothing with 3581 and 181
assert.deepEqual(presetPrefixes(preset('uniforms')), ['3581', '181', '182', '183', '188', '351134', '395']);
assert.equal(CPV_FULL.get('18800000'), 'Footwear');
assert.equal(CPV_FULL.get('35113400'), 'Protective and safety clothing');
// p04: the fuse tender (24615000) and the primers are under 2461 with 353
assert.deepEqual(presetPrefixes(preset('weapons')), ['353', '2461']);
assert.equal(CPV_FULL.get('24615000'), 'Fuses, caps, igniters and electric detonators');
assert.match(preset('weapons').label, /explosives and pyrotechnics/);
// p03: the mechanical spare parts the persona named
for (const c of ['35421000', '35521000', '35641000', '34320000', '34913000', '35340000']) assert.ok(preset('parts').codes.includes(c as never), c);
// p06: the service groups
assert.deepEqual(CPV_PRESETS.filter((p) => p.group === 'services').map((p) => presetPrefixes(p).join(',')),
  ['601,631,6352,637', '091', '79993,909', '555', '501', '806', '72']);
assert.equal(CPV_FULL.get('09100000'), 'Fuels');
assert.equal(CPV_FULL.get('80600000'), 'Training services in defence and security materials');

// ---------------------------------------------------------------- 5. the filters as chips
const ref = new Date('2026-10-12T08:00:00Z');
const f = parseTenderFilters({ q: 'boots', country: 'PT,ES', cpv: presetPrefixes(preset('uniforms')).join(','), from: '2026-10-12', to: '2026-10-19', status: 'all' });
const chips = filterChips(f, '/tenders', ref);
assert.deepEqual(chips.map((c) => c.label), ['“boots”', 'Uniforms, footwear and protective gear', 'Portugal', 'Spain', 'Every status', 'Deadline in the next 7 days']);
// each chip is the list without itself, the rest kept
assert.equal(chips.find((c) => c.label === 'Portugal')!.href, `/tenders?q=boots&country=ES&status=all&cpv=${encodeURIComponent('3581,181,182,183,188,351134,395')}&from=2026-10-12&to=2026-10-19`);
assert.ok(!chips.find((c) => c.label === '“boots”')!.href.includes('q='));
assert.deepEqual(filterChips(parseTenderFilters({}), '/tenders', ref), [], 'the defaults are no chip');
assert.deepEqual(filterChips(parseTenderFilters({ min: '100000', currency: 'PLN' }), '/tenders', ref).map((c) => c.label), ['Value PLN 100,000 to any']);

// ---------------------------------------------------------------- 6. buyers by the codes
assert.equal(defaultBuyerSort(['343']), 'cpv');
assert.equal(defaultBuyerSort(undefined), 'tenders');
assert.equal(parseBuyerFilters({ cpv: '343' }).sort, 'cpv', 'with codes the default is the order by them');
assert.equal(parseBuyerFilters({ sort: 'cpv' }).sort, 'tenders', 'without codes there is nothing to order by');
assert.equal(parseBuyerFilters({ cpv: '343', sort: 'tenders' }).sort, 'tenders');
assert.equal(toBuyerQuery(parseBuyerFilters({ cpv: '343' })), '?cpv=343', 'the default stays out of the address');
assert.equal(toBuyerQuery(parseBuyerFilters({ cpv: '343', sort: 'tenders' })), '?cpv=343&sort=tenders');
const byCode = queryBuyers({ cpv: ['44', '34', '60'], sort: 'cpv' }, ref).items;
assert.ok(byCode.length > 1 && byCode.every((b) => typeof b.cpvCount === 'number'));
for (let i = 1; i < byCode.length; i++) assert.ok((byCode[i - 1].cpvCount ?? 0) >= (byCode[i].cpvCount ?? 0), 'most under the codes first');
assert.ok(queryBuyers({}, ref).items.every((b) => b.cpvCount === null));

// ---------------------------------------------------------------- 6. suppliers: values, value order, TED view
assert.deepEqual(ignoredFilters({ sort: 'value-EUR', source: 'ted' }, 'suppliers'), []);
assert.deepEqual(ignoredFilters({ sort: 'value-XYZ', source: 'placsp' }, 'suppliers').length, 2);
const eur = querySuppliers({ sort: 'value-EUR' }).items.map((s) => s.name);
assert.deepEqual(eur.slice(0, 2), ['Demo Ordnance SA', 'Demo Airframes GmbH']);
assert.equal(querySuppliers({ sort: 'value-PLN' }).items[0].name, 'Demo Protective Textiles sp. z o.o.');
assert.ok(!querySuppliers({ source: 'ted' }).items.some((s) => s.country === 'ES'));
assert.equal(listValueLine([{ currency: 'EUR', amount: 1243802.4, count: 2, lotEstimates: 0 }, { currency: 'PLN', amount: 7e6, count: 2, lotEstimates: 0 }], 6),
  'Contract values: EUR 1,243,802 over 2 of 6 contracts; PLN 7,000,000 over 2');
assert.equal(listValueLine([], 3), 'Contract values: none stated for this company alone');

// ---------------------------------------------------------------- 7. the coverage constant, held to the sources
// The countries whose own tender portal or feed a migration registers (kind 'tender', a country), less the one-off Atlas load and
// the award results (read by the supplier map, not a tender source): exactly the constant's countries.
const migrations = join(process.cwd(), '..', 'backend', 'migrations');
const sql = readdirSync(migrations).filter((n) => n.endsWith('.sql')).map((n) => readFileSync(join(migrations, n), 'utf8')).join('\n');
const tenderSources = [...sql.matchAll(/\(\s*'([a-z_]+)',\s*'(?:[^']|'')*',\s*'([A-Z]{2})',\s*'tender'/g)]
  .filter(([, code]) => code !== 'pl_atlas' && !code.endsWith('_awards'));
assert.deepEqual([...new Set(tenderSources.map(([, , cc]) => cc))].sort(), Object.keys(NATIONAL_COVERAGE).sort(),
  'NATIONAL_COVERAGE names the countries of the tender sources');
assert.ok(sql.includes("'es_placsp_awards'"), 'Spain’s award results are a source');
assert.deepEqual(Object.entries(NATIONAL_COVERAGE).filter(([, n]) => n.awards).map(([c]) => c), ['ES'], 'only PLACSP award results are read');

assert.equal(coverageLine('PT'), 'Portugal: TED only; the national portal is not collected');
assert.equal(coverageLine('IT'), 'Italy: TED only; the national portal is not collected');
assert.equal(coverageLine('ES'), 'Spain: TED + PLACSP, awards too');
assert.match(coverageLine('NL'), /^Netherlands: TED \+ TenderNed \(since January 2026\); .*one buyer/);
assert.match(coverageLine('DE'), /^Germany: TED \+ the federal notice service \(since 25 October 2023\)/);
assert.equal(coverageLine('ES', 'awards'), "Spain: winners from TED and from PLACSP's award results");
assert.equal(coverageLine('FR', 'awards'), "France: winners from TED only; BOAMP's award notices are not read");
assert.equal(coverageLine('IT', 'awards'), 'Italy: winners from TED only; the national portal is not collected');
assert.deepEqual(coverageLines(['PT', 'PT', 'EU']), ['Portugal: TED only; the national portal is not collected.']);
assert.deepEqual(coverageLines(undefined), []);
assert.deepEqual(coverageLines(['DE', 'FR', 'PL', 'ES', 'IT', 'PT', 'NL']), [], 'seven lines say nothing');

console.log('wp98b.check: ok');
