/**
 * Self-check of WP-107 (round 3, 24 October 2026: readiness wizard and roadmap).
 *   1. the offering goes to the API (the roadmap leaves AQAP out for software and services) only when answered
 *   2. the EEA-recipient question is the wizard's (step 5) as well, and answering it there does not make a supplier
 *   3. the NATO clearance questions follow a "yes" or "not sure" to classified work (p01)
 *   4. stamping and harness processes; the ANSSI qualifications as certificates no rule reads
 *   5. the German AQAP issuer (now U in the seed) is said as "not verified" in the supplier roadmap (p03: no "Bundeswehr")
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { CERTIFICATES, ES_QUESTIONS, EU_QUESTION, PROCESSES, askedAt, emptyProfile, hasSupplier, stepOfField, supplierFields, toRequest, wizardAsks, type Profile } from './profile';
import type { Assessment } from './readiness-types';
import { supplierRoadmap } from './supplier-roadmap';

const base = (over: Partial<Profile> = {}): Profile => ({ ...emptyProfile(), country: 'BE', step: 6, ...over });

// 1. offering
assert.equal(toRequest(base())!.profile.offering, undefined, 'unanswered: not sent');
assert.equal(toRequest(base({ offering: 'software_services' }))!.profile.offering, 'software_services');
assert.equal(toRequest(base({ offering: 'products' }))!.profile.offering, undefined, 'products: nothing changes, nothing sent');

// 2. the EEA-recipient question
assert.ok(wizardAsks(EU_QUESTION));
assert.equal(stepOfField(EU_QUESTION), 5);
assert.equal(askedAt(EU_QUESTION), '/readiness?step=5', 'a wizard user is sent to step 5');
assert.equal(askedAt(EU_QUESTION, true), `/readiness/supplier#q-${EU_QUESTION}`, 'a supplier to its own page');
const eea = base({ supplier: { ...emptyProfile().supplier, answers: { [EU_QUESTION]: 'yes' } } });
assert.equal(hasSupplier(eea), false, 'the wizard answer alone does not make a supplier');
assert.equal(supplierFields(eea)[EU_QUESTION], true, 'and it is sent');
const iso27001 = base({ supplier: { ...emptyProfile().supplier, held: ['ISO27001'] } });
assert.equal(hasSupplier(iso27001), false, 'a certificate ticked in step 4 alone does not make a supplier');
assert.equal(hasSupplier(base({ supplier: { ...emptyProfile().supplier, cpv: ['34300000'] } })), true);

// 3. NATO clearance questions only with classified work
const nato = ES_QUESTIONS.find((q) => q.field === 'nato_classified_contract')!;
const es = (classified: Profile['classified'], answers: Record<string, string> = {}) =>
  ({ ...emptyProfile(), country: 'ES', classified, supplier: { ...emptyProfile().supplier, answers } }) as Profile;
assert.equal(nato.when!(es('no')), false);
assert.equal(nato.when!(es('yes')), true);
assert.equal(nato.when!(es('unsure')), true);
assert.equal(supplierFields(es('no', { nato_classified_contract: 'yes', nsfcc_held: 'no' })).nato_classified_contract, undefined, 'a leftover answer is not sent');
assert.equal(supplierFields(es('no', { nato_classified_contract: 'yes', nsfcc_held: 'no' })).nsfcc_held, undefined);
assert.equal(supplierFields(es('yes', { nato_classified_contract: 'yes' })).nato_classified_contract, true);

// 4. processes and certificates
assert.ok(PROCESSES.some((p) => p.value === 'stamping') && PROCESSES.some((p) => p.value === 'harness'));
for (const k of ['ISO27001', 'PASSI', 'SECNUMCLOUD', 'CSPN']) assert.ok(CERTIFICATES.some((c) => c.key === k && !c.code), k);

// 5. an unverified issuer (the German AQAP row, U since WP-107) is not printed as a body
const answer = {
  assessments: [{ programme: 'NATO-SUPPLY', name: 'NATO', kind: 'route', verdict: 'conditional', rules: [{ rule: 'NATO-AQAP', title: 'AQAP', outcome: 'info', obligation: 'conditional', requirement: 'REQ-AQAP2110', reason: 'r', asks: [], source: { url: '', ref: '', text: '', origin: 'notes', verificationStatus: 'S', lastReviewed: '2026-09-07' } }] }],
  general: [],
  roadmap: { steps: [{ order: 1, code: 'REQ-AQAP2110', name: 'AQAP 2110', category: 'quality', summary: '', status: 'not_held', optional: true, when: 'when a contract names it', blockingFor: [], neededFor: [], cost: null, days: null, variantUsed: null, branchNote: null, issuers: [{ country: 'DE', name: 'Bundeswehr', url: null, notes: null, status: 'U' }], issuerNote: null, priceNote: null, prerequisites: [], parallelWith: [], verificationStatus: 'S', lastReviewed: '2026-09-07', sourceUrl: '' }] },
  consultants: [],
} as unknown as Assessment;
const item = supplierRoadmap(answer, { ...emptyProfile(), country: 'DE' }).items.find((i) => i.key === 'REQ-AQAP2110')!;
assert.ok(item.issuers.every((t) => !t.includes('Bundeswehr')), JSON.stringify(item.issuers));
assert.match(item.issuers[0], /Not verified in our sources/);

console.log('wp107 ok');
