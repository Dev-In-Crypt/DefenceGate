/**
 * Self-check of WP-67 (the supplier roadmap and report): the three sample companies of WP-65 (`e2e/fixtures/profile-es-sup-*.json`, which
 * send exactly the generated requests) get, from the engine's answers (`assess-es-sup-*.json`), the red / amber / green list stated here:
 * prerequisites before what needs them, PECAL never red, Spain's NCAGE amber while no need justifies it, a cost or a time only from a
 * primary source, every "consultant needed" flag on the list, and an honest summary.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseProfile, toRequest } from './profile';
import { NOT_PRIMARY, supplierRoadmap, type RoadmapItem } from './supplier-roadmap';
import type { Assessment } from './readiness-types';

const json = (name: string) => JSON.parse(readFileSync(`e2e/fixtures/${name}.json`, 'utf8'));
const sample = (key: string) => {
  const profile = parseProfile(json(`profile-${key}`));
  assert.deepEqual(toRequest(profile), json(`request-${key}`), `${key}: the stored profile sends the generated request`);
  const answer = json(`assess-${key}`) as Assessment;
  return { profile, answer, plan: supplierRoadmap(answer, profile) };
};
const line = (i: RoadmapItem) => `${i.rag} ${i.key}`;
const at = (items: RoadmapItem[], key: string) => items.findIndex((i) => i.key === key);
const item = (items: RoadmapItem[], key: string) => { const i = items.find((x) => x.key === key); assert.ok(i, key); return i; };

if (process.env.WP67_PRINT) for (const k of ['es-sup-civil', 'es-sup-defence', 'es-sup-partial']) console.log(k, JSON.stringify(sample(k).plan, null, 1));

const SAMPLES = ['es-sup-civil', 'es-sup-defence', 'es-sup-partial'];

// ------------------------------------------------------------- the three companies, line by line
const civil = sample('es-sup-civil').plan;
assert.deepEqual(civil.items.map(line), [
  'green REQ-ISO9001', 'green IATF16949', 'red REQ-RID', 'amber REQ-PIC', 'amber REQ-NCAGE', 'amber REQ-AQAP2110', 'amber REQ-PECAL', 'amber REQ-EXPORT',
]);
// Spain's NCAGE: NATO supply asks for one, but the Spanish bureau needs a justified need, which this company does not have yet
assert.match(item(civil.items, 'REQ-NCAGE').reason ?? '', /no product bought by the Ministry/);
assert.equal(item(civil.items, 'REQ-NCAGE').status, 'A condition comes first.');
assert.match(item(civil.items, 'REQ-PIC').status, /^Only if you apply for EU funding/);
assert.equal(item(civil.items, 'IATF16949').status, 'In place: you hold it. No rule of this check reads it.');

const defence = sample('es-sup-defence').plan;
assert.deepEqual(defence.items.map(line), [
  'green REQ-NCAGE', 'green REQ-ISO9001', 'green REQ-AQAP2110', 'green REQ-RID', 'red REQ-FSC-ES', 'amber REQ-PIC', 'amber REQ-PECAL', 'amber REQ-EXPORT',
  'amber US-COMPONENTS',
]);
assert.match(item(defence.items, 'REQ-FSC-ES').reason ?? '', /access classified information/);

const partial = sample('es-sup-partial').plan;
assert.deepEqual(partial.items.map(line), [
  'green REQ-ISO9001', 'red REQ-NCAGE', 'red REQ-RID', 'amber REQ-PIC', 'amber REQ-AQAP2110', 'amber REQ-PECAL', 'amber REQ-EN9100', 'amber REQ-FSC-ES',
  'amber REQ-EXPORT', 'amber US-COMPONENTS',
]);
// what this company did not answer stays a question on its line
assert.ok(item(partial.items, 'REQ-NCAGE').asks.some((q) => /bought by the Ministry/.test(q)));
assert.ok(item(partial.items, 'US-COMPONENTS').asks.some((q) => /US origin/.test(q)));

for (const key of SAMPLES) {
  const { answer, plan } = sample(key);
  const items = plan.items;
  // a prerequisite always comes first (ISO 9001 and the RID before PECAL; ISO 9001 before AQAP 2110), whatever its colour
  for (const i of items) for (const name of i.after) {
    const pre = items.findIndex((x) => x.name === name);
    if (pre >= 0) assert.ok(pre < items.indexOf(i), `${key}: ${name} before ${i.key}`);
  }
  assert.ok(at(items, 'REQ-ISO9001') < at(items, 'REQ-PECAL'), `${key}: ISO 9001 before PECAL`);
  const rid = at(items, 'REQ-RID');
  assert.ok(rid >= 0 && rid < at(items, 'REQ-PECAL'), `${key}: RID before PECAL`);
  // PECAL is the chicken-and-egg of a first contract: never "needed now", always explained
  const pecal = item(items, 'REQ-PECAL');
  assert.equal(pecal.rag, 'amber', `${key}: PECAL is not a blocker`);
  assert.match(pecal.note ?? '', /not a block before a first contract/);
  // cost and time: a figure only where the requirement's source is primary. No primary source in the seed states one, so every line
  // that is not in place says so; the figures of the research notes (NCAGE "free of charge", NSPA) are not printed.
  for (const i of items) {
    if (i.rag === 'green') { assert.equal(i.cost, null); continue; }
    const step = answer.roadmap.steps.find((s) => s.code === i.key);
    if (step?.origin === 'primary') assert.equal(i.cost, 'Not stated in the sources', `${key}: ${i.key} primary, no figure stated`);
    else assert.equal(i.cost, NOT_PRIMARY, `${key}: ${i.key}`);
    assert.ok(!/free|EUR|USD|days|months/i.test(`${i.cost} ${i.time}`), `${key}: ${i.key} prints no figure`);
  }
  // every "consultant needed" flag of the answer is on the list, and every line that is not in place names its source (or has none: US-COMPONENTS)
  for (const f of answer.consultants ?? []) assert.ok(items.some((i) => i.consultant.includes(f.text)), `${key}: flag ${f.key} on the list`);
  for (const i of items) if (i.rag !== 'green' && i.key !== 'US-COMPONENTS') assert.ok(i.source?.url.startsWith('http'), `${key}: ${i.key} has a source`);
  assert.equal(plan.counts.green + plan.counts.red + plan.counts.amber, items.length);
  assert.match(plan.summary, /does not win a contract/);
}
assert.ok(civil.summary.startsWith('2 items are in place, 1 is needed now on your answers, and 5 depend on a contract, a condition or an answer. 2 items need a specialist.'));
assert.ok(partial.summary.startsWith('1 item is in place, 2 are needed now'));

// ------------------------------------------------------------- what the samples do not show
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const { profile: cp, answer: ca } = sample('es-sup-civil');
const rules = (a: Assessment) => [...a.assessments, ...a.general].flatMap((p) => p.rules);
// a company that wants the PECAL certificate and lacks the RID: the rule is "not met", the line stays amber (the step waits for a contract)
const wants = clone(ca);
Object.assign(rules(wants).find((r) => r.rule === 'ES-PECAL-CONTRACT')!, { outcome: 'not_met' });
assert.equal(item(supplierRoadmap(wants, cp).items, 'REQ-PECAL').rag, 'amber');
// a foreign investor without the Council of Ministers authorisation: a red line of its own, with the specialist
const foreign = clone(sample('es-sup-defence').answer);
Object.assign(rules(foreign).find((r) => r.rule === 'ES-FOREIGN-CAPITAL')!, { outcome: 'not_met', consultant: 'Foreign-capital authorisation: ask a lawyer.' });
const fc = item(supplierRoadmap(foreign, sample('es-sup-defence').profile).items, 'ES-FOREIGN-CAPITAL');
assert.equal(fc.rag, 'red');
assert.deepEqual(fc.consultant, ['Foreign-capital authorisation: ask a lawyer.']);
assert.equal(fc.cost, NOT_PRIMARY);
// a step whose source is primary and states a figure prints it
const priced = clone(ca);
Object.assign(priced.roadmap.steps.find((s) => s.code === 'REQ-RID')!, { cost: { min: 100, max: 100, currency: 'EUR', basis: 'not_stated', text: null, alt: null, label: null } });
assert.equal(item(supplierRoadmap(priced, cp).items, 'REQ-RID').cost, 'EUR 100');
// a funding programme's "to obtain" is never "needed now" for a supplier; a supply route's is
assert.equal(item(civil.items, 'REQ-PIC').rag, 'amber');
// names passed in by the page win over the stored labels for what is held
assert.equal(item(supplierRoadmap(ca, cp, { 'REQ-ISO9001': 'ISO 9001 quality management' }).items, 'REQ-ISO9001').name, 'ISO 9001 quality management');
console.log('wp67 ok');
