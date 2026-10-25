/**
 * Self-check of WP-125 (verification round 6, 25 October 2026): the readiness check's results count as missing only what its five steps ask,
 * the one question of step 1 sets both inputs the rules read, the report's sector words follow the codes, and the demo search's
 * "typed only" words. Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { AUTOMOTIVE_SET, codeKind } from './cpv';
import { askedAt, askedInSteps, emptyProfile, kindOf, toRequest, unanswered, withKind, type Profile } from './profile';
import { expand, matchesSlots } from './search-terms';

// ---------------------------------------------------------------- 1. after the five steps, missing = asked by the steps

// The Spanish route's missing answers of the e2e fixture (the API's answer for a Spanish wizard profile): every one is asked somewhere,
// the supplier page's are not "in the steps", and the steps' own are
const es = JSON.parse(readFileSync('e2e/fixtures/assess-es.json', 'utf8'));
const mod = es.assessments.find((a: { programme: string }) => a.programme === 'ES-MOD');
const p: Profile = { ...emptyProfile(), country: 'ES', step: 6 };
for (const m of mod.missing as { field: string }[]) {
  // the results link a question of the steps to its step, any other to the supplier page (rules.tsx)
  if (!askedInSteps(m.field, p)) assert.match(askedAt(m.field, true, p) ?? '', /^\/readiness\/supplier#q-/, `${m.field}: asked on the supplier page`);
}
assert.equal(askedAt('certified_recipient', true, p), '/readiness/supplier#q-receives_eea_defence_products', 'a hidden follow-up: its parent there');
for (const f of ['REQ-RID', 'pecal_certificate_wanted', 'nato_icb_bid', 'foreign_capital', 'us_components', 'certified_recipient']) {
  assert.equal(askedInSteps(f, p), false, `${f}: the supplier page's, not the steps'`);
}
for (const f of ['legal_form', 'handles_classified', 'receives_eea_defence_products', 'REQ-ISO9001', 'org_kind', 'ua_partner']) {
  assert.equal(askedInSteps(f, p), true, `${f}: a question of the five steps`);
}

// ---------------------------------------------------------------- 2. one question of what the organisation is

const base: Profile = { ...emptyProfile(), country: 'PL', legalForm: 'legal_person', control: 'no' };
assert.equal(kindOf(base), '');
assert.ok(unanswered(base).some((u) => u.step === 1 && u.question === 'What kind of organisation you are'));
const company = withKind(base, 'company');
assert.deepEqual([company.applicantKind, company.orgKind], ['company_or_research', 'company']);
assert.equal(kindOf(company), 'company');
const req = toRequest(company)!.profile as Record<string, unknown>;
assert.equal(req.applicant_kind, 'company_or_research');
assert.equal(req.org_kind, 'company');
const uni = withKind(company, 'university');
assert.deepEqual([uni.applicantKind, uni.orgKind], ['company_or_research', 'university']);
const ministry = withKind(uni, 'contracting_authority');
assert.deepEqual([ministry.applicantKind, ministry.orgKind], ['contracting_authority', '']);
assert.equal(kindOf(ministry), 'contracting_authority');
assert.equal(toRequest(ministry)!.profile.applicant_kind, 'contracting_authority');
assert.equal((toRequest(ministry)!.profile as Record<string, unknown>).org_kind, undefined, 'a public body sends no kind of company');
assert.ok(!unanswered(ministry).some((u) => u.question === 'What kind of organisation you are'), 'a public body has answered it');
// a profile saved before the merge: "a company or research body" without its kind is still asked; a SEAP is answered
assert.equal(kindOf({ ...base, applicantKind: 'company_or_research' }), '');
assert.equal(kindOf({ ...base, applicantKind: 'seap' }), 'seap');
assert.equal(kindOf({ ...base, applicantKind: '', orgKind: 'research' }), 'research');

// ---------------------------------------------------------------- 4. the report's sector words follow the codes

assert.equal(codeKind(['31611000', '31612000', '35422000']), 'goods', 'a cable-harness maker (p03) is not the car industry');
assert.equal(codeKind(['31611000', '35420000']), 'goods');
assert.equal(codeKind([...AUTOMOTIVE_SET]), 'automotive');
assert.equal(codeKind(['34300000', '34100000', '35421000', '42600000', '44300000']), 'automotive', 'the civil Spanish fixture profile');
assert.equal(codeKind(['34300000', '31611000']), 'automotive', 'wiring sets beside vehicle parts');

// ---------------------------------------------------------------- 5. the demo search: "foundry" is searched only when typed

const castings = expand(['castings']);
assert.deepEqual(castings.groups.map((g) => g.id), ['castings']);
assert.ok(!castings.slots[0].some((a) => /^(foundry|fonderie|gießerei|odlewnia)$/i.test(a.join(' '))), 'castings does not search "foundry"');
assert.ok(!matchesSlots(castings.slots, ['Switzerland – Foundry moulds – IWB, Wasserleitungsrohre (Guss) und Formstücke'], 'IWB'), 'the water-pipe tender');
assert.ok(matchesSlots(castings.slots, ['Aluminium castings for gearboxes'], null));
assert.ok(matchesSlots(castings.slots, ['Lieferung von Gussteilen'], null));
const foundry = expand(['foundry']);
assert.deepEqual(foundry.groups.map((g) => g.id), ['castings'], 'typed, "foundry" still searches the castings group');
assert.ok(matchesSlots(foundry.slots, ['Aluminium castings for gearboxes'], null));
assert.ok(matchesSlots(foundry.slots, ['Foundry products for the navy'], null), 'and itself');

console.log('wp125 ok');
