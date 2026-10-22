/**
 * Self-check of WP-65 (the supplier profile): storage version 3 reads versions 1 and 2 without losing an answer, the supplier block is read
 * field by field, the page sends exactly the generated requests of the three sample companies (`e2e/fixtures/request-es-sup-*.json`, whose
 * open questions the backend counts), an empty answer is never sent, the Spanish questions carry the engine's own words, and the CPV
 * search finds whole words of the official titles only.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cpvDictionaryTitle, cpvSearch } from './cpv';
import {
  CERTIFICATES, ES_QUESTIONS, REGISTRATIONS, cpvProblem, emptyProfile, emptySupplier, exportProfile, hasSupplier, holds, importProfile,
  monthProblem, naceProblem, parseProfile, savedSupplier, supplierAsks, supplierProblems, toRequest, wizardAsks, withHeld, type Profile,
} from './profile';

const fixture = (key: string) => JSON.parse(readFileSync(`e2e/fixtures/request-${key}.json`, 'utf8'));
const cert = (key: string) => [...CERTIFICATES, ...REGISTRATIONS].find((c) => c.key === key)!;
const answers = (o: Record<string, 'yes' | 'no' | 'unsure'>) => o;
const CPV5 = ['34300000', '34100000', '35421000', '42600000', '44300000'];

// ------------------------------------------------------------- version 3, and versions 1 and 2 read without losing answers
const v2 = {
  version: 2, step: 6, updatedAt: '2026-10-21T10:00:00.000Z', name: 'Fundiciones X', sizeClass: 'medium', country: 'ES', legalForm: 'legal_person', applicantKind: 'company_or_research',
  management: 'same', managementCountry: '', control: 'no', uaOccupied: '', uaPartner: 'no', seapPartner: '', regime: 'none', componentPct: '15', restricted: 'no',
  uaEeaComponents: 'no', safeRole: 'other_supplier', statuses: { 'REQ-ISO9001': 'held', 'REQ-RID': 'held' }, classified: 'no', exportIntent: 'within_eu',
};
const read = parseProfile(v2);
assert.equal(read.version, 3, 'written back as version 3');
for (const [k, v] of Object.entries(v2)) if (k !== 'version') assert.deepEqual((read as unknown as Record<string, unknown>)[k], v, `version 2 answer ${k} kept`);
assert.deepEqual(read.supplier, emptySupplier(), 'a version 2 block has an empty supplier profile');
assert.equal(parseProfile({ ...v2, version: 1, managementSameCountry: false, managementCountry: 'FR' }).managementCountry, 'FR', 'version 1 still read');
assert.equal(parseProfile({ ...v2, version: 1 }).statuses['REQ-ISO9001'], 'held');
assert.deepEqual(parseProfile({ ...v2, version: 4 }), emptyProfile(), 'an unknown version is refused');
// a version 2 profile sends what it sent before: no supplier field appears in its request
assert.equal(Object.keys(toRequest(read)!.profile).length, 14);
assert.equal(hasSupplier(read), false);
// import of an older file, and export and import of a version 3 one
const old = importProfile(JSON.stringify(v2));
assert.ok(old.ok && old.profile.version === 3 && old.profile.name === 'Fundiciones X');

// ------------------------------------------------------------- the supplier block, field by field
const hostile = parseProfile({ ...v2, version: 3, supplier: {
  region: 'x'.repeat(200), foreignOwner: 'maybe', foreignCountry: 'France', nace: '25.50', cpv: ['34300000', '34300000', '3430', 'DROP TABLE', ...Array.from({ length: 30 }, (_, i) => String(30000000 + i))],
  processes: ['casting', 'hacking'], held: ['IATF16949', 'REQ-PIC', 'NSPA'], expiry: { ISO9001: '2027-05', IATF16949: '2027-13', EVIL: '2027-01' }, usComponents: 'yes',
  answers: { nato_icb_bid: 'yes', pecal_certificate_wanted: 'perhaps', legal_form: 'yes', __proto__: 'x' },
} });
const s = hostile.supplier;
assert.equal(s.region.length, 60);
assert.equal(s.foreignOwner, '');
assert.equal(s.foreignCountry, '');
assert.equal(s.cpv.length, 15, 'at most 15, each 8 digits, once');
assert.equal(s.cpv[0], '34300000');
assert.ok(s.cpv.every((c) => /^\d{8}$/.test(c)));
assert.deepEqual(s.processes, ['casting']);
assert.deepEqual(s.held, ['IATF16949', 'NSPA'], 'only the certificates and registrations no requirement covers');
assert.deepEqual(s.expiry, { ISO9001: '2027-05' });
assert.deepEqual(s.answers, { nato_icb_bid: 'yes' }, 'only the questions of the Spanish route, with an answer');
const back = importProfile(exportProfile(hostile));
assert.ok(back.ok);
if (back.ok) assert.deepEqual({ ...back.profile, updatedAt: null }, { ...hostile, updatedAt: null }, 'what was written is read back');

// ------------------------------------------------------------- validation
assert.equal(naceProblem(''), null);
for (const ok of ['25', '25.5', '25.50', 'C25.50', 'c25.50', ' 29.32 ']) assert.equal(naceProblem(ok), null, ok);
for (const bad of ['2', '255', '25.501', 'Z25', '25-50', 'abc']) assert.ok(naceProblem(bad), bad);
assert.equal(cpvProblem([]), null, 'WP-73: no CPV code is required (no rule reads them)');
assert.equal(cpvProblem(CPV5.slice(0, 4)), null);
assert.equal(cpvProblem(CPV5), null);
assert.ok(cpvProblem(Array.from({ length: 16 }, (_, i) => String(i)))?.includes('at most 15'));
assert.equal(monthProblem(''), null);
assert.equal(monthProblem('2027-05'), null);
for (const bad of ['2027-13', '2027-5', '05/2027', '2027']) assert.ok(monthProblem(bad), bad);
const es: Profile = { ...emptyProfile(), country: 'ES' };
assert.deepEqual(supplierProblems(emptyProfile()).map((x) => x.id), ['sp-country']);
assert.deepEqual(supplierProblems({ ...es, supplier: { ...emptySupplier(), cpv: CPV5, nace: 'x' } }).map((x) => x.id), ['sp-nace']);
const iso = withHeld(es, cert('ISO9001'), true);
assert.equal(iso.statuses['REQ-ISO9001'], 'held', 'a certificate with a requirement is that requirement\'s status (the wizard\'s step 4)');
assert.ok(holds(iso, cert('ISO9001')));
const isoBad = { ...iso, supplier: { ...iso.supplier, cpv: CPV5, expiry: { ISO9001: '2027-13' } } };
assert.deepEqual(supplierProblems(isoBad).map((x) => x.id), ['sp-expiry-ISO9001']);
const unticked = withHeld(isoBad, cert('ISO9001'), false);
assert.equal(unticked.statuses['REQ-ISO9001'], 'not_held');
assert.deepEqual(unticked.supplier.expiry, {}, 'an unticked certificate drops its month');
assert.deepEqual(withHeld(es, cert('NSPA'), true).supplier.held, ['NSPA']);
assert.deepEqual(withHeld(withHeld(es, cert('NSPA'), true), cert('NSPA'), false).supplier.held, []);

// ------------------------------------------------------------- RID and PECAL: unknown until the page is saved, then "not held" unless ticked
assert.equal(toRequest(es)!.statuses['REQ-RID'], undefined);
assert.equal(toRequest(savedSupplier(es))!.statuses['REQ-RID'], 'not_held');
assert.equal(toRequest(savedSupplier(es))!.statuses['REQ-PECAL'], 'not_held');
assert.equal(toRequest(savedSupplier(es))!.statuses['REQ-HSES-ES'], undefined, 'the page does not ask the HSES');
assert.equal(toRequest(savedSupplier(withHeld(es, cert('RID'), true)))!.statuses['REQ-RID'], 'held');
// WP-73: every certificate and registration the page shows is "not held" once saved unticked; the Spanish ones only for a Spanish company
assert.deepEqual(savedSupplier({ ...es, country: 'PL' }).statuses, { 'REQ-ISO9001': 'not_held', 'REQ-EN9100': 'not_held', 'REQ-AQAP2110': 'not_held', 'REQ-AQAP2310': 'not_held', 'REQ-NCAGE': 'not_held' }, 'Spanish requirements are not filled in for a company elsewhere');

// ------------------------------------------------------------- the three sample companies send exactly the generated requests
const sup = (over: Partial<Profile['supplier']>, rest: Partial<Profile> = {}): Profile =>
  savedSupplier({ ...emptyProfile(), country: 'ES', sizeClass: 'medium', classified: 'no', ...rest, supplier: { ...emptySupplier(), cpv: CPV5, ...over } });
const civil = sup({
  region: 'ES-PV', nace: '24.53', processes: ['casting', 'machining'], held: ['IATF16949'], expiry: { ISO9001: '2027-05' }, foreignOwner: 'no', usComponents: 'no',
  answers: answers({ pecal_certificate_wanted: 'no', pecal_2310_target: 'no', ncage_need_justified: 'no', specific_defence_use: 'no', nato_classified_contract: 'no',
    nato_icb_bid: 'no', receives_eea_defence_products: 'no' }),
}, { control: 'no', statuses: { 'REQ-ISO9001': 'held' } });
assert.deepEqual(toRequest(civil), fixture('es-sup-civil'));
const defence = sup({
  processes: ['machining', 'electronics'], foreignOwner: 'yes', foreignCountry: 'FR', usComponents: 'yes',
  answers: answers({ pecal_certificate_wanted: 'yes', pecal_system_9_months: 'yes', pecal_prior_contract: 'no', pecal_2310_target: 'no', specific_defence_use: 'yes',
    homologation_mandatory: 'no', homologated: 'yes', stores_classified: 'no', nato_classified_contract: 'no', nato_icb_bid: 'yes', rid_capabilities_declared: 'yes',
    foreign_investor_authorised: 'yes', receives_eea_defence_products: 'yes', certified_recipient: 'no', ncage_need_justified: 'yes', nsfcc_held: 'yes' }),
}, { classified: 'yes', statuses: { 'REQ-ISO9001': 'held', 'REQ-AQAP2110': 'held', 'REQ-RID': 'held', 'REQ-NCAGE': 'held' } });
// hidden answers are kept and not sent: "homologated" (the list does not make it mandatory), "ncage_need_justified" (NCAGE held), "nsfcc_held" (no NATO classified contract)
assert.deepEqual(toRequest(defence), fixture('es-sup-defence'));
assert.equal(defence.supplier.answers.homologated, 'yes');
const partial = sup({ processes: ['assembly'], foreignOwner: 'no', usComponents: 'unsure' }, { control: 'no', statuses: { 'REQ-ISO9001': 'held' } });
assert.deepEqual(toRequest(partial), fixture('es-sup-partial'), '"I am not sure" and empty answers are not sent');
// the Spanish questions are not sent for a company elsewhere; foreign capital and US components are
const pl = toRequest({ ...defence, country: 'PL' })!.profile;
assert.equal(pl.nato_icb_bid, undefined);
assert.equal(pl.foreign_capital, true);
assert.equal(pl.us_components, true);
assert.ok(JSON.stringify(toRequest(civil)).length < 4096, 'under the proxy body limit');
for (const leak of ['24.53', 'ES-PV', 'casting', '34300000', 'IATF', 'FR', 'medium']) {
  assert.ok(!JSON.stringify(toRequest(defence)).includes(`"${leak}"`) && !JSON.stringify(toRequest(civil)).includes(`"${leak}"`), `${leak} stays in the browser`);
}

// ------------------------------------------------------------- the questions are the engine's own, and the results link them to this page
const engine = readFileSync('../backend/dgate/readiness/engine.py', 'utf8');
for (const q of ES_QUESTIONS) {
  const m = new RegExp(`"${q.field}": \\{"kind": "(\\w+)",(?: "values": [^,]+,)?\\s*"label": "([^"]+)"`).exec(engine);
  assert.ok(m, `${q.field} is a field of engine.SUPPLIER_FIELDS`);
  assert.equal(q.label, m[2], `${q.field}: the engine's words`);
  assert.equal(q.kind === 'enum', m[1] === 'enum', `${q.field}: kind`);
}
for (const f of ['foreign_capital', 'us_components', 'REQ-RID', 'REQ-PECAL', 'nato_icb_bid', 'profile.certified_recipient']) assert.ok(supplierAsks(f), f);
// WP-73: the HSEM and HSES are asked there now (REQ-FSC-ES, REQ-HSES-ES); the PIC is not (the wizard's step 4)
for (const f of ['REQ-FSC-ES', 'REQ-HSES-ES']) assert.ok(supplierAsks(f), f);
// WP-68: the German and dual-use questions are asked there now (wp68.check.ts); the PIC and the legal form still are not
for (const f of ['REQ-PIC', 'legal_form']) assert.ok(!supplierAsks(f), f);
assert.ok(wizardAsks('handles_classified') && supplierAsks('REQ-NCAGE'), 'a field both ask is linked to the wizard first (rules.tsx)');

// ------------------------------------------------------------- CPV search: code prefix, curated words, whole words of the titles
assert.deepEqual(cpvSearch('3542').map((c) => c.code), ['35420000', '35421000', '35421100', '35422000']);
assert.ok(cpvSearch('drone').some((c) => c.code === '35613000') && cpvSearch('drone').some((c) => c.code === '34711200'), 'a curated word');
assert.ok(cpvSearch('vehicles').some((c) => c.code === '34300000'));
assert.ok(cpvSearch('parts vehicles').every((c) => /part/i.test(c.title) && /vehicle/i.test(c.title)), 'every word');
assert.ok(!cpvSearch('gun').some((c) => /Gunmetal/.test(c.title)), 'never a piece of a longer word');
assert.deepEqual(cpvSearch(''), []);
assert.deepEqual(cpvSearch('zz'), []);
assert.ok(cpvSearch('a', 3).length <= 3);
assert.equal(cpvSearch('35', 20).length, 20, 'at most 20 shown');
assert.equal(cpvDictionaryTitle('34711200'), 'Non-piloted aircraft', 'a curated code has its official title');
assert.equal(cpvDictionaryTitle('34300000'), 'Parts and accessories for vehicles and their engines');
assert.equal(cpvDictionaryTitle('99999999'), null);
for (const c of CPV5) assert.ok(cpvDictionaryTitle(c), c);

console.log('wp65 checks passed');
