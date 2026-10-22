/**
 * Self-check of WP-68 (the supplier page's German and dual-use questions, and the sample of /readiness/spain-automotive): the questions carry
 * the engine's own words and choices, a German supplier's page sends exactly the generated request (`e2e/fixtures/request-de-sup.json`, whose
 * outcomes the backend states), a hidden or unasked answer is never sent, the stored block keeps only valid answers, the results link the
 * questions to the page, and the sample shows only a well-formed live answer.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  DE_QUESTIONS, DUAL_USE_QUESTION, EXPORT_HOLDING, answerLabel, askedAt, emptyProfile, emptySupplier, exportProfile, importProfile, parseProfile,
  savedSupplier, supplierAsks, toRequest, withClearance, type Answer, type Profile,
} from './profile';
import { SAMPLE_CPV, isDemand } from './demand';
import mockDemand from './mock/demand.json';

const fixture = (key: string) => JSON.parse(readFileSync(`e2e/fixtures/request-${key}.json`, 'utf8'));

// ------------------------------------------------------------- the engine's words, kinds and choices
const engine = readFileSync('../backend/dgate/readiness/engine.py', 'utf8');
for (const q of [...DE_QUESTIONS, DUAL_USE_QUESTION]) {
  const m = new RegExp(`"${q.field}": \\{"kind": "(\\w+)",(?: "values": (\\([^)]*\\)|\\w+),)?\\s*"label": "([^"]+)"`).exec(engine);
  assert.ok(m, `${q.field} is a field of engine.SUPPLIER_FIELDS`);
  assert.equal(q.label, m[3], `${q.field}: the engine's words`);
  assert.equal(q.kind === 'enum', m[1] === 'enum', `${q.field}: kind`);
  if (q.options) assert.deepEqual(q.options.map((o) => o.value), [...m[2].matchAll(/"(\w+)"/g)].map((x) => x[1]), `${q.field}: the engine's values`);
}
// every German field the engine's German rules read is asked (DE-SUE reads none of its own)
const seed = JSON.parse(readFileSync('../backend/seeds/requirements.json', 'utf8')) as { rules: { code: string; applies_when?: unknown; condition?: unknown }[] };
const fieldsOf = (x: unknown): string[] => (x && typeof x === 'object' ? Object.entries(x).flatMap(([k, v]) => (k === 'field' ? [v as string] : fieldsOf(v))) : []);
const german = new Set(seed.rules.filter((r) => r.code.startsWith('DE-')).flatMap((r) => [...fieldsOf(r.applies_when), ...fieldsOf(r.condition)]));
const wizard = new Set(['country', 'handles_classified', 'export_intent']);
assert.deepEqual([...german].filter((f) => !wizard.has(f)).sort(), DE_QUESTIONS.map((q) => q.field).sort(), 'the German rules read exactly these questions');

// ------------------------------------------------------------- a German supplier sends exactly the generated request
const de = (answers: Record<string, Answer>, rest: Partial<Profile> = {}): Profile => savedSupplier({
  ...emptyProfile(), country: 'DE', classified: 'yes', exportIntent: 'outside_eu', control: 'no', statuses: { 'REQ-ISO9001': 'held' }, ...rest,
  supplier: { ...emptySupplier(), foreignOwner: 'no', usComponents: 'no', answers: { receives_eea_defence_products: 'no', ...answers } },
});
const DE_ANSWERS: Record<string, Answer> = {
  de_vs_vertraulich: 'yes', ghb_admitted: 'no', sibe_appointed: 'yes', de_vs_nfd: 'yes', vsnfd_declaration_signed: 'yes', vsnfd_merkblatt: 'no',
  de_ausfuhrliste: 'unsure', dualuse_annex_i: 'unsure',
};
const sup = withClearance(de(DE_ANSWERS), 'REQ-EXPORT', 'no');
assert.ok(EXPORT_HOLDING.when(sup), 'the export authorisation is asked once the item may be listed');
assert.deepEqual(toRequest(sup), fixture('de-sup'));

// hidden answers are kept and not sent: the follow-ups after a "no", every German answer without classified access, the dual-use answer
// when the product is military or exported only within the EU, the export list when nothing is exported
const p1 = toRequest(de({ ...DE_ANSWERS, de_vs_vertraulich: 'no', de_vs_nfd: 'no' }))!.profile;
for (const f of ['ghb_admitted', 'sibe_appointed', 'vsnfd_declaration_signed', 'vsnfd_merkblatt']) assert.equal(p1[f], undefined, `${f} hidden after a no`);
assert.equal(p1.de_vs_vertraulich, false);
const p2 = toRequest(de(DE_ANSWERS, { classified: 'no' }))!.profile;
for (const q of DE_QUESTIONS.filter((x) => x.field !== 'de_ausfuhrliste')) assert.equal(p2[q.field], undefined, `${q.field}: no classified access`);
assert.equal(p2.de_ausfuhrliste, 'unsure', 'the export list does not depend on classified work');
assert.equal(toRequest(de(DE_ANSWERS, { regime: 'military' }))!.profile.dualuse_annex_i, undefined);
assert.equal(toRequest(de(DE_ANSWERS, { regime: 'none' }))!.profile.dualuse_annex_i, undefined);
assert.equal(toRequest(de(DE_ANSWERS, { exportIntent: 'within_eu' }))!.profile.dualuse_annex_i, undefined);
assert.equal(toRequest(de(DE_ANSWERS, { exportIntent: 'none' }))!.profile.de_ausfuhrliste, undefined);
assert.equal(toRequest(de(DE_ANSWERS, { regime: 'dual_use' }))!.profile.dualuse_annex_i, 'unsure', 'asked of a dual-use product');
// the German questions are not sent for a company elsewhere; the dual-use one is (its rule has no country condition)
const es = toRequest(de(DE_ANSWERS, { country: 'ES' }))!.profile;
for (const q of DE_QUESTIONS) assert.equal(es[q.field], undefined, `${q.field} not sent for Spain`);
assert.equal(es.dualuse_annex_i, 'unsure');
// "I am not sure" on the export authorisation leaves it unknown; yes is held
assert.equal(toRequest(withClearance(de(DE_ANSWERS), 'REQ-EXPORT', 'unsure'))!.statuses['REQ-EXPORT'], 'unknown');
assert.equal(toRequest(withClearance(de(DE_ANSWERS), 'REQ-EXPORT', 'yes'))!.statuses['REQ-EXPORT'], 'held');
assert.equal(EXPORT_HOLDING.when(de({ ...DE_ANSWERS, de_ausfuhrliste: 'neither', dualuse_annex_i: 'no' })), false);
// a profile without these answers sends what it sent before WP-68 (the WP-65 fixtures are checked byte for byte in wp65.check.ts)
assert.equal(Object.keys(toRequest(de({}))!.profile).filter((f) => DE_QUESTIONS.some((q) => q.field === f) || f === DUAL_USE_QUESTION.field).length, 0);

// ------------------------------------------------------------- storage: only valid answers are kept (the block stays version 3)
const stored = parseProfile({ ...JSON.parse(exportProfile(sup)), supplier: { ...sup.supplier, answers: {
  de_ausfuhrliste: 'yes', dualuse_annex_i: 'part_i_a', ghb_admitted: 'neither', sibe_appointed: 'yes', 'REQ-EXPORT': 'no', unknown_field: 'yes',
} } });
assert.equal(stored.version, 3);
assert.deepEqual(stored.supplier.answers, { sibe_appointed: 'yes', 'REQ-EXPORT': 'no' }, 'each answer only from its own choices');
const back = importProfile(exportProfile(sup));
assert.ok(back.ok && back.profile.supplier.answers.de_ausfuhrliste === 'unsure' && back.profile.supplier.answers.dualuse_annex_i === 'unsure');
assert.equal(answerLabel(DE_QUESTIONS.find((q) => q.field === 'de_ausfuhrliste')!, 'part_i_b'), 'Yes, Part I Section B (national dual-use list)');
assert.equal(answerLabel(DUAL_USE_QUESTION, 'unsure'), 'Not sure');

// ------------------------------------------------------------- the results link the questions to the page
for (const f of [...DE_QUESTIONS.map((q) => q.field), DUAL_USE_QUESTION.field]) assert.ok(supplierAsks(f), f);
assert.equal(askedAt('de_vs_nfd'), '/readiness/supplier#sp-germany');
assert.equal(askedAt('ghb_admitted'), '/readiness/supplier#sp-germany');
assert.equal(askedAt('dualuse_annex_i'), '/readiness/supplier#sp-export');
assert.equal(askedAt('de_ausfuhrliste'), '/readiness/supplier#sp-export');
assert.equal(askedAt('REQ-EXPORT'), '/readiness?step=4', 'the export authorisation stays linked to step 4, where everyone is asked');

// ------------------------------------------------------------- the live sample: a well-formed answer only
assert.deepEqual([...SAMPLE_CPV], ['34300000', '34100000', '35421000', '42600000', '44300000']);
assert.ok(isDemand(mockDemand), 'the demo answer has the shape');
for (const bad of [null, {}, { ...mockDemand, total: null }, { ...mockDemand, byCountry: [{ country: 'ES' }] }, { ...mockDemand, coverage: 3 }]) assert.equal(isDemand(bad), false);

console.log('wp68 checks passed');
