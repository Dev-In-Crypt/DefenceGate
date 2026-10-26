/**
 * Self-check of WP-141 (verification round 8, 25 October 2026, r8-site/text/call114-profile.txt): with a saved profile, a call whose action
 * admits only some kinds of applicant (EDIP common procurement 108-112, SEAP support 114, EDPCI preparation 193) said "Blocked by: an established
 * SEAP" over a row "Who may apply: Check", and printed the blocker as the fragment "Not allowed. an established SEAP.". The row now says the
 * rule's verdict in a sentence, and the blocker is not listed twice. The calls are what production served (data/wp109-calls.json, 114;
 * data/wp93-pairs.json, 110 112 114 193; data/wp102-pairs.json, 111). backend/tests/unit/test_wp141.py checks the API's twin.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import type { EligibilityFacts } from './eligibility-check';
import { boxLines, callFit, fitLabel, isLine, linesSummary, verdictLines, WHO_MAY_APPLY, type FitResult } from './fit';
import { emptyProfile, parseProfile, type Profile } from './profile';

const sme: Profile = { ...emptyProfile(), country: 'ES', legalForm: 'legal_person', applicantKind: 'company_or_research', orgKind: 'company', control: 'no' };
const seap: Profile = { ...sme, applicantKind: 'seap' };

/** What every box of the call page shows for a blocked call: one "Who may apply" row, a no, in sentences; the blocker named once. */
function oneRow(r: FitResult, only: RegExp, what: string) {
  assert.equal(r.fit, 'no', what);
  const lines = verdictLines(r);
  const who = lines.filter((l) => l.label === WHO_MAY_APPLY);
  assert.equal(who.length, 1, `${what}: one row "Who may apply"`);
  assert.equal(who[0].verdict, 'no', `${what}: the row says what the verdict says`);
  assert.match(who[0].reason, only, `${what}: the rule as a sentence`);
  assert.ok(!lines.some((l) => l.key === 'entity'), `${what}: the document's "Check" row gave way`);
  assert.ok(lines.every((l) => /^[A-Z]/.test(l.reason)), `${what}: no reason is a lower-case fragment: ${lines.map((l) => l.reason).join(' | ')}`);
  // (other programme rules that block, a Ukrainian company and the EDIP Programme, stay rows of their own)
  const rule = r.blockedBy.find((b) => b.startsWith(`${WHO_MAY_APPLY}: `))!.slice(WHO_MAY_APPLY.length + 2);
  assert.ok(!lines.some((l) => l.key.startsWith('programme-') && l.reason.includes(rule)), `${what}: the rule is not listed again as "Rule of the programme or the action"`);
  assert.match(linesSummary(lines), /is a no|are a no/);
  // the box of "Your readiness for this call" and the first screen (apply-summary.tsx) read the same lines
  assert.deepEqual(boxLines(r).lines.filter((l) => l.label === WHO_MAY_APPLY), who);
  assert.ok(isLine(`${WHO_MAY_APPLY}: ${rule}`, r.result?.lines ?? []), `${what}: the blocker is the row (apply-summary.tsx lists it once)`);
  // the badge of the list is unchanged
  assert.match(fitLabel(r).word, /^Blocked by: /);
}

// ---------------------------------------------------------------- 114 as production served it, a company and a SEAP

const page = JSON.parse(readFileSync('lib/data/wp109-calls.json', 'utf8')).calls['114'];
const call114 = { state: 'read' as const, facts: page.facts as EligibilityFacts, programme: page.programme, topic: page.topicId };
const r114 = callFit(call114, sme, null);
oneRow(r114, /^Only an established SEAP may apply to this call\. /, '114 company');
assert.equal(fitLabel(r114).word, 'Blocked by: an established SEAP', 'the badge as before');
assert.ok(!verdictLines(r114).some((l) => / \. ?[a-z]|Not allowed\. [a-z]/.test(l.reason)));
assert.ok(verdictLines(r114).find((l) => l.label === WHO_MAY_APPLY)!.quote, 'the row keeps the document\'s sentence');
// a SEAP may apply: the document's row stays as it was
const s114 = callFit(call114, seap, null);
assert.notEqual(s114.fit, 'no');
assert.ok(!verdictLines(s114).some((l) => l.key === 'who'), 'nothing is replaced where the rule does not block');

// ---------------------------------------------------------------- every profile x EDIP call of the verified sets where the rule blocks

const ONLY: Record<string, RegExp> = {
  '110': /^Only contracting authorities, international organisations, SEAPs and the EDA may apply/, '111': /^Only contracting authorities/,
  '112': /^Only contracting authorities/, '114': /^Only an established SEAP may apply/, '193': /^Only a SEAP or a group of Member States may apply/,
};
let blocked = 0;
for (const file of ['lib/data/wp93-pairs.json', 'lib/data/wp102-pairs.json']) {
  const data = JSON.parse(readFileSync(file, 'utf8'));
  for (const [id, c] of Object.entries(data.after as Record<string, { programme: string; topic: string; state: 'read'; facts: Record<string, { value: unknown; note: string | null; quote: string; scope: string }> }>)) {
    if (!ONLY[id]) continue;
    const facts = Object.fromEntries(Object.entries(c.facts).map(([k, f]) => [k, { ...f, confidence: 1 }])) as unknown as EligibilityFacts;
    for (const key of Object.keys(data.profiles)) {
      // each set's own reading of its profiles (wp93.check.ts, wp102.check.ts profileOf)
      const p = file.includes('wp93') ? parseProfile({ ...data.profiles[key].stored, ...data.profiles[key].answers, version: 4 }) : parseProfile(data.profiles[key].stored);
      const r = callFit({ state: c.state, programme: c.programme, topic: c.topic, facts }, p, data.assessments[key]);
      if (!r.blockedBy.some((b) => b.startsWith(`${WHO_MAY_APPLY}: `))) continue;
      oneRow(r, ONLY[id], `${key} x ${id}`);
      blocked += 1;
    }
  }
}
assert.equal(blocked, 50, 'wp93: 10 profiles x 110 112 114 193; wp102: 10 profiles x 111');

// ---------------------------------------------------------------- a call whose rules were not read, and a programme rule's title

const unread = callFit({ state: 'not_read', facts: {} as EligibilityFacts, programme: 'EDF', topic: 'EDF-EDIP-P-2026-FNLC-CSA-PREP' }, sme, null);
oneRow(unread, ONLY['193'], '193 unread');
// a programme's blocking rule whose last part alone is a fragment keeps its subject ("Legal entity: a legal person ...")
const prog: FitResult = { fit: 'no', result: null, conditions: [], blockedBy: ['European Defence Fund: Legal entity: a legal person, or an entity without legal personality that is accepted'] };
assert.equal(verdictLines(prog)[0].reason, 'Legal entity: a legal person, or an entity without legal personality that is accepted.');
const fact: FitResult = { ...prog, blockedBy: ['European Defence Industry Programme (EDIP): the Programme: Established in the Union or an associated country'] };
assert.equal(verdictLines(fact)[0].reason, 'Established in the Union or an associated country.', 'unchanged where the last part is a sentence head');

console.log('wp141 checks passed');
