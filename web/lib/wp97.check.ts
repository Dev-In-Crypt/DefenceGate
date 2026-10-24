/**
 * Self-check of WP-97 (persona round of 23 October 2026, section B: the supplier report for every country and for services).
 *   1. the kind of codes chooses the words; the Spanish automotive material only for a Spanish company with automotive codes
 *   2. own country first; dealers of parts and tyres apart as competitors or distributors; buyer amounts in words; the open-now link
 *   3. the national routes: Germany and Poland from the repository's primary sources, "Not covered yet ... Check with ..." elsewhere;
 *      the NCAGE words one sentence in the requirements page, the roadmap, the report and the route; Spain's own requirements hidden
 *      for another country
 *   4. the services path: services processes and certificates parsed and kept; the suggested code sets are official codes
 *   5. "I am not sure" is an answer; every missing-answer link lands on a question the supplier page shows for these answers
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { AMMUNITION_SET, AUTOMOTIVE_SET, CODE_SETS, MACHINING_SET, SERVICES_SET, codeKind } from './cpv';
import { CPV_FULL } from './cpv-full';
import { COUNTRY_ROUTES, countryRoute } from './country-routes';
import { approachGroups, buyerAmount, openHref, ownFirst, type Demand } from './demand';
import {
  CERTIFICATES, DE_QUESTIONS, ES_CLEARANCES, ES_QUESTIONS, SERVICE_PROCESSES, askedAt, emptyProfile, notSure, parseProfile, providesServices,
  requirementCountry, supplierFields, type Profile,
} from './profile';
import { NSPA_NCAGE_URL, issuerFor, ncageText } from './readiness';
import type { Assessment } from './readiness-types';
import { supplierRoadmap } from './supplier-roadmap';
import mock from './mock/demand.json';

const fixture = <T,>(name: string): T => JSON.parse(readFileSync(join('e2e', 'fixtures', name), 'utf8')) as T;
const profile = (over: Omit<Partial<Profile>, 'supplier'> & { supplier?: Partial<Profile['supplier']> }): Profile => {
  const p = emptyProfile();
  return { ...p, ...over, supplier: { ...p.supplier, ...(over.supplier ?? {}) } };
};

// ---------------------------------------------------------------- 1. the words by codes and country
assert.equal(codeKind([...AUTOMOTIVE_SET]), 'automotive');
assert.equal(codeKind([...SERVICES_SET]), 'services');
assert.equal(codeKind([...AMMUNITION_SET]), 'ammunition');
assert.equal(codeKind(['35641000', '34731000', '42141000', '35521000']), 'machining');
assert.equal(codeKind(['60000000', '63100000', '34300000']), 'services', 'mostly services codes');
assert.equal(codeKind(['33100000', '18100000']), 'goods');
assert.equal(codeKind([]), 'none');

// ---------------------------------------------------------------- 2. own country first, dealers apart, amounts, open now
const demo = mock as unknown as Demand;
assert.deepEqual(ownFirst(demo.byCountry, 'NL').map((c) => c.country), ['NL', 'ES', 'DE', 'FR', 'PL']);
assert.deepEqual(ownFirst(demo.byCountry, 'IT').map((c) => c.country), ['ES', 'DE', 'FR', 'PL', 'NL'], 'a country outside the map: order kept');
const es = approachGroups(demo.approach, 'ES');
assert.ok(es.dealers.length > 0 && es.dealers.every((w) => w.distributor && !w.prime), 'the dealers apart');
assert.ok(es.dealers.some((w) => /CONTINENTAL TIRES/.test(w.name)) && es.dealers.some((w) => /^FERRETER/i.test(w.name)), 'tyres and hardware');
assert.ok(es.home.every((w) => !w.distributor) && es.others.every((w) => !w.distributor), 'no dealer among the direct suppliers');
assert.equal(es.home.length + es.primes.length + es.others.length + es.dealers.length, demo.approach.winners.length, 'every winner once');
assert.equal(buyerAmount({ slug: 'x', name: 'x', core: true, procurements: 3 }), null, 'an older answer: no amount');
assert.equal(buyerAmount({ slug: 'x', name: 'x', core: true, procurements: 3, awardedValue: [] }), null);
assert.equal(buyerAmount({ slug: 'x', name: 'x', core: true, procurements: 3, awardedValue: [
  { currency: 'EUR', amount: 1200000.4, count: 3, lotEstimates: 0 }, { currency: 'PLN', amount: 40000, count: 1, lotEstimates: 0 }] }),
'EUR 1,200,000 over 3 contracts; PLN 40,000 over 1 contract');
assert.equal(openHref(demo, 'ES'), `/tenders?country=ES&cpv=${[...new Set(demo.codes.map((c) => c.prefix))].join(',')}`, 'built from the prefixes without openNow');
const withOpen = { ...demo, byCountry: demo.byCountry.map((c) => (c.country === 'DE' ? { ...c, openNow: { count: 4, atLeast: false, href: '/tenders?country=DE&cpv=343' } } : c)) };
assert.equal(openHref(withOpen, 'DE'), '/tenders?country=DE&cpv=343', "the answer's own link first");

// ---------------------------------------------------------------- 3. the national routes
assert.deepEqual(countryRoute('ES'), [], 'Spain has its route in the rules');
const de = countryRoute('DE');
assert.deepEqual(de.map((l) => l.key), ['de-buyer', 'de-notices', 'de-export', 'de-classified', 'ncage', 'de-quality']);
assert.ok(de.find((l) => l.key === 'de-export')!.text.includes('BAFA') && de.find((l) => l.key === 'de-export')!.link!.url.startsWith('https://www.gesetze-im-internet.de/awv_2013/'));
assert.ok(de.find((l) => l.key === 'de-buyer')!.text.includes('BAAINBw') && de.find((l) => l.key === 'de-buyer')!.text.includes('Bekanntmachungsservice'));
const pl = countryRoute('PL');
assert.ok(pl.some((l) => l.text.includes('Agencja Uzbrojenia')) && pl.some((l) => /weapons, ammunition and explosives/.test(l.text)));
for (const l of [...de, ...pl, ...countryRoute('NL'), ...countryRoute('FR')]) {
  // an open line says plainly what is not covered and whom to ask; no cost, time or issuer is invented
  if (l.open) assert.match(l.text, /^Not covered yet for (the )?[A-Z][a-z]+( [A-Z][a-z]+)?: .+\. Check with .+\.$/, l.text);
  assert.doesNotMatch(l.text, /\b(EUR|PLN|days|weeks|months)\b/, `no figure: ${l.text}`);
  if (l.link && !l.link.url.startsWith('/')) assert.match(l.link.url, /^https:\/\//);
}
const nl = countryRoute('NL');
assert.equal(nl[0].title, 'Supplying the armed forces of the Netherlands');
// every route link outside this site is a source already in the repository
const known = ['https://oeffentlichevergabe.de/', 'https://www.gesetze-im-internet.de/awv_2013/__8.html', 'https://www.bmwe-sicherheitsforum.de/ghb/allgemeines/222,0,0,1,0.html', 'https://ezamowienia.gov.pl/', NSPA_NCAGE_URL,
  // WP-105: the export authorities of the Netherlands and Italy, the issuers of REQ-EXPORT in the requirements seed
  'https://www.rijksoverheid.nl/themas/economie/exportcontrole-strategische-goederen/vraag-en-antwoord/exportcontrole-strategische-goederen/wanneer-heb-ik-een-vergunning-nodig-voor-de-export-van-militaire-goederen',
  'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1990-07-09;185~art7bis'];
const seed = readFileSync(join('..', 'backend', 'seeds', 'requirements.json'), 'utf8') + readFileSync(join('..', 'docs', 'sources', 'de_national.md'), 'utf8')
  + readFileSync(join('..', 'backend', 'dgate', 'sources', 'ezamowienia.py'), 'utf8');
for (const l of Object.values(COUNTRY_ROUTES).flat()) if (l.link && !l.link.url.startsWith('/')) {
  assert.ok(known.includes(l.link.url), l.link.url);
  assert.ok(seed.includes(l.link.url.replace(/\/$/, '')), `in the repository: ${l.link.url}`);
}
// NCAGE: the same sentence on the requirements page (issuerFor), the roadmap and the report (issuerFor via supplierRoadmap), and the route
const unverified = { country: 'DE', name: 'National codification bureau (NCB) of the country', url: null, notes: 'UNVERIFIED', verificationStatus: 'U' as const };
const a = issuerFor('REQ-NCAGE', [unverified], 'DE');
assert.equal(a.kind, 'unverified');
assert.equal(a.kind === 'unverified' ? a.text : '', ncageText('DE'));
assert.equal(de.find((l) => l.key === 'ncage')!.text, ncageText('DE'));
assert.match(ncageText('PL'), /^Not covered yet for Poland: which office issues NCAGE codes .+ Check with NSPA/);
const assessDe = fixture<Assessment>('assess-de-sup.json');
const deProfile = profile({ country: 'DE', statuses: { 'REQ-NCAGE': 'not_held' } });
const ncageItem = supplierRoadmap(assessDe, deProfile).items.find((i) => i.key === 'REQ-NCAGE');
if (ncageItem) {
  assert.ok(!ncageItem.issuers.some((x) => x.startsWith('National codification bureau')), 'the report never prints the unverified row');
  assert.ok(ncageItem.issuers.includes(ncageText('DE')), ncageItem.issuers.join(' | '));
}
// Spain's own requirements for Spain only
for (const c of ['REQ-RID', 'REQ-PECAL', 'REQ-REOCE', 'REQ-FSC-ES', 'REQ-HSES-ES']) assert.equal(requirementCountry(c), 'ES');
for (const c of ['REQ-NCAGE', 'REQ-PIC', 'REQ-AQAP2110', 'REQ-EXPORT', 'REQ-ISO9001']) assert.equal(requirementCountry(c), null);

// ---------------------------------------------------------------- 4. services
const svc = parseProfile({ ...profile({ country: 'NL', offering: 'software_services' }), supplier: { ...emptyProfile().supplier,
  processes: ['logistics', 'fuel', 'catering', 'casting', 'bogus'], held: ['VCA', 'ISO14001', 'ISO45001', 'ISO50001', 'ISO27001', 'bogus'] } });
assert.ok(providesServices(svc));
assert.deepEqual(svc.supplier.processes, ['logistics', 'fuel', 'catering', 'casting'], 'service processes are kept; unknown ones dropped');
assert.deepEqual(svc.supplier.held, ['VCA', 'ISO14001', 'ISO45001', 'ISO50001', 'ISO27001']);
for (const k of ['VCA', 'ISO14001', 'ISO45001', 'ISO50001', 'ISO27001']) assert.ok(CERTIFICATES.some((c) => c.key === k && !c.code), `${k}: a certificate no rule reads`);
assert.deepEqual(SERVICE_PROCESSES.map((x) => x.value), ['logistics', 'transport', 'fuel', 'facility', 'catering', 'maintenance', 'training', 'it_services']);
for (const set of CODE_SETS) for (const c of set.codes) assert.ok(CPV_FULL.has(c), `${set.key}: ${c} is an official CPV code`);
assert.ok(MACHINING_SET.length <= 15 && SERVICES_SET.length <= 15 && AMMUNITION_SET.length <= 15);
assert.deepEqual(new Set(SERVICES_SET.map((c) => c.slice(0, 2))), new Set(['60', '63', '09', '79', '90', '55', '50', '80', '72']));
assert.ok(AMMUNITION_SET.includes('24615000') && AMMUNITION_SET.includes('35330000'), 'fuses and ammunition');

// ---------------------------------------------------------------- 5. "not sure" is an answer; links land on shown questions
const marta = profile({ country: 'ES', classified: 'unsure', supplier: { answers: { pecal_certificate_wanted: 'unsure', ncage_need_justified: 'unsure', specific_defence_use: 'no' } } });
assert.ok(notSure(marta, 'handles_classified') && notSure(marta, 'pecal_certificate_wanted') && notSure(marta, 'profile.ncage_need_justified'));
assert.ok(!notSure(marta, 'pecal_system_9_months') && !notSure(marta, 'specific_defence_use'));
// the persona's three questions "referenced but missing": shown now that the answer they follow is "not sure", and linked to themselves
for (const f of ['pecal_system_9_months', 'pecal_prior_contract', 'stores_classified']) {
  const q = ES_QUESTIONS.find((x) => x.field === f)!;
  assert.ok(q.when!(marta), `${f} is asked after "not sure"`);
  assert.equal(askedAt(f, true, marta), `/readiness/supplier#q-${f}`);
}
assert.ok(ES_CLEARANCES.find((q) => q.code === 'REQ-FSC-ES')!.when(marta), 'the HSEM is asked after "not sure" to classified access');
assert.ok(ES_CLEARANCES.find((q) => q.code === 'REQ-HSES-ES')!.when({ ...marta, supplier: { ...marta.supplier, answers: { ...marta.supplier.answers, stores_classified: 'unsure' } } }));
assert.ok('pecal_system_9_months' in supplierFields({ ...marta, supplier: { ...marta.supplier, answers: { ...marta.supplier.answers, pecal_system_9_months: 'yes' } } }));
// hidden follow-ups link to the question that shows them, recursively
const empty = profile({ country: 'ES' });
assert.equal(askedAt('pecal_system_9_months', true, empty), '/readiness/supplier#q-pecal_certificate_wanted');
assert.equal(askedAt('homologated', true, empty), '/readiness/supplier#q-specific_defence_use');
assert.equal(askedAt('stores_classified', true, empty), '/readiness/supplier#q-classified');
assert.equal(askedAt('REQ-HSES-ES', true, empty), '/readiness/supplier#q-classified', 'through stores_classified, itself hidden');
assert.equal(askedAt('REQ-HSES-ES', true, marta), '/readiness/supplier#q-stores_classified');
assert.equal(askedAt('foreign_investor_authorised', true, empty), '/readiness/supplier#q-foreign_capital');
assert.equal(askedAt('ncage_need_justified', true, empty), '/readiness/supplier#q-ncage_need_justified');
// every question of the Spanish and German rules: its link is its own field when shown, else the field of a question that is shown
const page = (p: Profile): Set<string> => new Set([
  'q-classified', 'q-foreign_capital',
  ...(p.country === 'ES' ? ES_QUESTIONS.filter((q) => !q.when || q.when(p)).map((q) => `q-${q.field}`) : []),
  ...(p.country === 'ES' ? ES_CLEARANCES.filter((q) => q.when(p)).map((q) => `q-${q.code}`) : []),
  ...(p.country === 'DE' && ['yes', 'unsure'].includes(p.classified) ? DE_QUESTIONS.filter((q) => q.field !== 'de_ausfuhrliste' && (!q.when || q.when(p))).map((q) => `q-${q.field}`) : []),
]);
for (const p of [empty, marta, profile({ country: 'ES', classified: 'yes', supplier: { answers: { nato_classified_contract: 'yes' } } }),
  profile({ country: 'DE', classified: 'unsure' }), profile({ country: 'DE', classified: 'yes', supplier: { answers: { de_vs_vertraulich: 'unsure' } } })]) {
  const fields = p.country === 'ES' ? [...ES_QUESTIONS.map((q) => q.field), ...ES_CLEARANCES.map((q) => q.code)] : DE_QUESTIONS.filter((q) => q.field !== 'de_ausfuhrliste' && ['yes', 'unsure'].includes(p.classified)).map((q) => q.field);
  // es_defence_material_list: its rules apply only to a military product (product_regime), the answer that shows it, so it is never
  // missing while hidden
  for (const f of fields.filter((x) => x !== 'es_defence_material_list' || p.regime === 'military')) {
    const href = askedAt(f, true, p)!;
    assert.ok(page(p).has(href.split('#')[1]), `${p.country} ${p.classified}: ${f} -> ${href}`);
  }
}

console.log('wp97 self-check: ok');
