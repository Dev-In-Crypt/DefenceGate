/**
 * Self-check of WP-89 (UX audit of 22 October 2026, section 4: the supplier path, persona Marta, a Valencian automotive parts maker).
 *   1. "who to approach": the winners of the company's own country first, the primes apart, the rest after (lib/demand.ts)
 *   2. CPV search: an automotive supplier's words find the product codes, products before the machines that make them, a suggested set
 *   3. the /buyers and /market CPV filters are read from the URL as /tenders reads them
 *   4. a supplier leads with its supply routes; the PIC and the EU questions only for one that wants EU funding; a missing answer is
 *      asked on the supplier page
 *   5. one cost statement per requirement; regional grants of the company's own region, or a plain sentence; closed calls marked
 *   6. a winner's supplier page is linked with the report's codes and countries
 *   7. the contract values' summary line carries the total
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { AUTOMOTIVE_SET, cpvForWords, cpvSearch, isMachineCode, productNote } from './cpv';
import { CPV_FULL } from './cpv-full';
import { approachGroups, demandRequest, supplierHref, type Demand } from './demand';
import { GRANTS, isClosed, noRegionalGrant, regionalGrants } from './es-support';
import { ignoredFilters, parseBuyerFilters, parseMarketFilters, toBuyerQuery } from './filters';
import { EU_FUNDING_FIELDS, SUPPLY_ROUTES, askedAt, emptyProfile, hasSupplier, parseProfile, roadmapProgrammes, toRequest, wantsEuFunding, type Profile } from './profile';
import { NOT_STATED, costStatement, formatRange, timeStatement } from './readiness';
import type { Assessment } from './readiness-types';
import { supplierRoadmap } from './supplier-roadmap';
import { totalLine } from './value-totals';
import mock from './mock/demand.json';

const fixture = <T,>(name: string): T => JSON.parse(readFileSync(join('e2e', 'fixtures', name), 'utf8')) as T;

// ---------------------------------------------------------------- 1. who to approach: own country first
const demo: Demand = mock;
const es = approachGroups(demo.approach, 'ES');
assert.ok(es.home.length > 0 && es.home.every((w) => w.country === 'ES' && !w.prime), 'Spanish direct suppliers');
assert.ok(es.home.some((w) => /Suyfa/i.test(w.name)) && es.home.some((w) => /RECAMBIOS COLON CATARROJA/.test(w.name)), 'the audit\'s names');
assert.ok(es.primes.every((w) => w.prime) && es.primes[0].country === 'ES', 'a prime of the own country leads the primes (Indra before Saab)');
assert.equal(es.home.length + es.primes.length + es.others.length, demo.approach.winners.length, 'every named winner once');
assert.ok(es.home.every((w, i, xs) => i === 0 || xs[i - 1].contracts >= w.contracts), 'most contracts first');
const de = approachGroups(demo.approach, 'DE');
assert.equal(de.home.length, 0, 'a German company of this demo has no home winner');
assert.equal(de.others.length, es.home.length, 'the Spanish winners are "other countries" for it');

// ---------------------------------------------------------------- 2. CPV search for an automotive supplier
const codes = (q: string) => cpvSearch(q, 50, CPV_FULL).map((c) => c.code);
const castings = codes('castings');
assert.equal(castings[0], '44470000', 'castings: Cast-iron products first');
const castingMachines = castings.indexOf('43720000');
assert.ok(castingMachines > castings.indexOf('34320000'), 'the casting machines after the products');
assert.ok(castings.filter((c) => !isMachineCode(c, CPV_FULL)).every((c) => castings.indexOf(c) < (castingMachines < 0 ? Infinity : castingMachines)), 'every product before the machines');
for (const q of ['machined', 'machined parts', 'machining', 'turned parts', 'cnc']) assert.ok(codes(q).slice(0, 3).includes('34320000'), `${q}: machined part codes`);
assert.ok(codes('machining').indexOf('34320000') < codes('machining').indexOf('42612000'), 'machining: the parts before the machining centre');
for (const [q, code] of [['forgings', '42141100'], ['stampings', '34330000'], ['rubber parts', '19510000'], ['plastic parts', '19520000'], ['wiring harness', '31611000'],
  ['filters', '42913000'], ['seats', '34370000'], ['windscreen', '39299200'], ['coatings', '44113330'], ['paint', '44810000'], ['fasteners', '44530000'], ['bolts', '44531400']] as const) {
  assert.ok(codes(q).slice(0, 8).includes(code), `${q}: ${code}`);
}
assert.match(productNote('castings') ?? '', /no code for castings as such.*43720000/);
assert.equal(productNote('drone zzzz'), null);
assert.ok(isMachineCode('43720000', CPV_FULL) && isMachineCode('42612000', CPV_FULL) && isMachineCode('42636000', CPV_FULL), 'machines');
assert.ok(!isMachineCode('44470000', CPV_FULL) && !isMachineCode('42913000', CPV_FULL), 'filters are products');
// the supplier map's product search reads the same words (cpvForWords)
assert.deepEqual(cpvForWords('castings').prefixes.sort(), ['34312', '3432', '35421', '4447']);
assert.equal(new Set(AUTOMOTIVE_SET).size, AUTOMOTIVE_SET.length);
for (const c of AUTOMOTIVE_SET) assert.ok(CPV_FULL.has(c), `${c} is an official code`);
assert.ok(AUTOMOTIVE_SET.length <= 15, 'the set fits a profile');

// ---------------------------------------------------------------- 3. CPV filters of /buyers and /market
const b = parseBuyerFilters({ cpv: '343, 35120000-1, x', country: 'ES' });
assert.deepEqual(b.cpv, ['343', '35120000']);
assert.equal(toBuyerQuery(b), '?country=ES&cpv=343%2C35120000');
assert.deepEqual(parseBuyerFilters({}).cpv, undefined);
assert.deepEqual(ignoredFilters({ cpv: '343,abc' }, 'buyers'), ['Ignored filter: cpv=abc (CPV codes are 2 to 8 digits)']);
assert.deepEqual(parseMarketFilters({ cpv: '343', year: '2025' }, 2026), { year: 2025, cpv: ['343'] });
assert.deepEqual(parseMarketFilters({}, 2026), {});

// ---------------------------------------------------------------- 4. a supplier leads with its supply routes
const civil = fixture<Profile>('profile-es-sup-civil.json');
const p = parseProfile(civil);
assert.equal(p.supplier.euFunding, '', 'an older profile reads with no answer');
assert.ok(hasSupplier(p) && !wantsEuFunding(p), 'a supplier page only: a supplier first');
assert.deepEqual(roadmapProgrammes(p), [...SUPPLY_ROUTES]);
const yes = { ...p, supplier: { ...p.supplier, euFunding: 'yes' as const } };
assert.ok(wantsEuFunding(yes) && roadmapProgrammes(yes) === null);
assert.ok(wantsEuFunding(emptyProfile()), 'the readiness check alone is about EU funding');
assert.ok(wantsEuFunding({ ...p, step: 6 }), 'a finished readiness check too');
assert.ok(!wantsEuFunding({ ...p, step: 6, supplier: { ...p.supplier, euFunding: 'no' } }), 'unless it says no');
assert.equal(parseProfile({ ...civil, supplier: { ...civil.supplier, euFunding: 'yes' } }).supplier.euFunding, 'yes', 'stored and read back');
assert.equal(toRequest(p)?.programmes, undefined, 'the results ask every programme (the roadmap adds the routes)');
// the routes-only answer the roadmap asks for (generated by the engine): no PIC, no funding programme
const routes = fixture<Assessment>('assess-es-sup-civil-routes.json');
assert.deepEqual(routes.assessments.map((a) => a.programme).sort(), [...SUPPLY_ROUTES].sort());
assert.ok(!routes.roadmap.steps.some((s) => s.code === 'REQ-PIC'), 'no PIC step');
const full = fixture<Assessment>('assess-es-sup-civil.json');
assert.ok(full.roadmap.steps.some((s) => s.code === 'REQ-PIC' && s.blockingFor.length > 0), 'the full answer had the PIC "needed now"');
assert.deepEqual(fixture<{ programmes: string[] }>('request-es-sup-civil-routes.json').programmes, [...SUPPLY_ROUTES]);
// a missing answer is asked on the supplier page for a supplier, in the readiness check otherwise
for (const f of EU_FUNDING_FIELDS) assert.equal(askedAt(f, true), '/readiness/supplier#sp-eu', f);
assert.equal(askedAt('profile.legal_form', true), '/readiness/supplier#sp-eu');
assert.equal(askedAt('handles_classified', true), '/readiness/supplier#q-classified');
assert.equal(askedAt('export_intent', true), '/readiness/supplier#q-export_intent');
assert.equal(askedAt('REQ-EXPORT', true), '/readiness/supplier#sp-export');
assert.equal(askedAt('pecal_certificate_wanted', true), '/readiness/supplier#q-pecal_certificate_wanted');
assert.equal(askedAt('legal_form'), '/readiness?step=1', 'the readiness check keeps its own steps');
// every question the Spanish route misses on the audit's profile is asked on the supplier page
const audit = fixture<Assessment>('assess-es-sup-partial.json');
const mod = audit.assessments.find((a) => a.programme === 'ES-MOD')!;
assert.ok(mod.missing.length > 0);
for (const m of mod.missing) assert.match(askedAt(m.field, true) ?? '', /^\/readiness\/supplier#/, `${m.field} is asked on the supplier page`);
for (const a of [...audit.assessments, ...audit.general]) for (const m of a.missing) assert.ok(!(askedAt(m.field, true) ?? '').startsWith('/readiness?step='), `${a.programme} ${m.field}`);

// ---------------------------------------------------------------- 5. one cost statement; grants of the own region
const ncage = full.roadmap.steps.find((s) => s.code === 'REQ-NCAGE')!;
const rid = full.roadmap.steps.find((s) => s.code === 'REQ-RID')!;
assert.equal(costStatement(ncage.cost), 'Free of charge (NSPA)');
assert.equal(costStatement(rid.cost), NOT_STATED);
assert.equal(timeStatement(rid.days), NOT_STATED);
assert.equal(formatRange(null), NOT_STATED, 'the roadmap totals say it in the same words');
const plan = supplierRoadmap(full, p);
assert.equal(plan.items.find((i) => i.key === 'REQ-NCAGE')?.cost, 'Free of charge (NSPA)', 'the report says what the roadmap says');
assert.equal(plan.items.find((i) => i.key === 'REQ-RID')?.cost, 'Not stated by the source');
const vc = regionalGrants('REQ-RID', 'ES-VC');
assert.deepEqual(vc, { grants: [], none: true }, 'Comunitat Valenciana: none of its own, said so');
assert.match(noRegionalGrant('Comunitat Valenciana'), /^No programme of Comunitat Valenciana in our sources pays for this step\. Ask your regional development agency/);
assert.ok(!/IVACE/.test(noRegionalGrant('Comunitat Valenciana')), 'no agency our sources do not name');
assert.deepEqual(regionalGrants('REQ-RID', 'ES-GA').grants.map((g) => g.region), ['ES-GA'], 'Galicia: its own only');
assert.ok(regionalGrants('REQ-RID', '').grants.length >= 3 && !regionalGrants('REQ-RID', '').none, 'no region chosen: every one');
assert.deepEqual(regionalGrants('REQ-NCAGE', 'ES-VC'), { grants: [], none: false }, 'a step no programme covers says nothing');
assert.deepEqual(GRANTS.filter(isClosed).map((g) => g.region).sort(), ['ES-AR', 'ES-EX', 'ES-GA']);

// ---------------------------------------------------------------- 6. the link to a winner's page carries the codes
const req = demandRequest(p);
assert.ok(req);
assert.equal(supplierHref('12-suyfa', req), `/suppliers/12-suyfa?cpv=${req.cpv.join('%2C')}&buyerCountry=ES%2CDE%2CFR%2CPL%2CNL`);
assert.equal(supplierHref('12-suyfa', null), '/suppliers/12-suyfa');

// ---------------------------------------------------------------- 7. the summary line of contract values
assert.equal(totalLine({ byCurrency: [], of: 3, withoutValue: 3, shared: 0 }, 'contract'), 'no stated value');
assert.equal(totalLine({ byCurrency: [{ currency: 'EUR', amount: 1234567.4, count: 3, lotEstimates: 0 }, { currency: 'PLN', amount: 5000, count: 1, lotEstimates: 0 }], of: 5, withoutValue: 1, shared: 0 }, 'contract'),
  'EUR 1,234,567 over 3 contracts; PLN 5,000 over 1 contract; 1 of 5 contracts state none');
assert.equal(totalLine({ byCurrency: [{ currency: 'EUR', amount: 10, count: 1, lotEstimates: 0 }], of: 1, withoutValue: 0, shared: 0 }, 'contract'), 'EUR 10 over 1 contract');

console.log('wp89 ok');
