/**
 * Self-check of WP-137: the call's own limits on who may apply (Art. 22.5 of the Horizon Europe Regulation, the EuroHPC JU calls 138-143;
 * the China control restriction of 154) come with the answer, and a company controlled from outside the eligible countries is not told
 * "nothing known blocks you" where the call admits it only on its exception (guarantees). The facts of 140 are the ones /v1/fit/facts
 * serves (data/wp102-pairs.json, `after`). Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CONTROL_WAY_ROUND, check, type EligibilityFacts } from './eligibility-check';
import { CONTROL_WORD, callFit, fitLabel, fitOrder, type CallFacts } from './fit';
import { whoLimits } from './funding-path';
import { parseProfile } from './profile';

const data = JSON.parse(readFileSync('lib/data/wp102-pairs.json', 'utf8'));
const c140 = data.after['140'];
const facts = c140.facts as EligibilityFacts;
const call: CallFacts = { state: 'read', programme: c140.programme, topic: c140.topic, facts };

// ---- 1. the limits beside "Companies can take part"
assert.equal(whoLimits({ whoMayApply: 'companies', whoMayApplyLimits: [] }), null, 'no limit, no rows');
assert.equal(whoLimits({ whoMayApply: 'companies' }), null, 'an older API build');
const est = 'participation is limited to legal entities established in Member States or Participating States of the EuroHPC JU';
const ctl = 'entities established in an eligible country but which are directly or indirectly controlled by China or by a legal entity established in China are not eligible to participate in the action.';
const both = whoLimits({ whoMayApply: 'companies', whoMayApplyLimits: [
  { kind: 'established', quote: est, note: '' }, { kind: 'control', quote: ctl, note: 'Participation is possible only with guarantees.' }] });
assert.ok(both && both.lead.startsWith('Companies can take part, but only within these limits'), 'the badge answer holds within them');
assert.deepEqual(both?.rows.map((r) => r.label), ['Where you must be established', 'Control from elsewhere']);
assert.equal(both?.rows[0].value, `“${est}”`);
assert.ok(both?.rows[1].value.endsWith('Participation is possible only with guarantees.'), 'the note follows the sentence');
assert.equal(whoLimits({ whoMayApply: null, whoMayApplyLimits: [{ kind: 'control', quote: ctl, note: '' }] })?.lead, 'The call’s own conditions limit who may take part:');

// ---- 2. the readiness check (140, the call page's form and the saved profile)
assert.equal(facts.ownership_control_restriction?.scope, 'topic', 'the restriction is the call’s own (rule_readings)');
const form = check(facts, { country: 'ES', orgType: 'sme', hasPartners: '', controlledAbroad: 'yes', controller: 'other_non_eu' }, { programme: 'HORIZON', topic: c140.topic });
const line = form.lines.find((l) => l.key === 'control');
assert.equal(line?.verdict, 'check');
assert.ok(line?.reason.startsWith(CONTROL_WAY_ROUND), 'the line of a restriction with a way round');
const us = check(facts, { country: 'US', orgType: 'sme', hasPartners: '', controlledAbroad: 'no' }, { programme: 'HORIZON', topic: c140.topic });
assert.equal(us.lines.find((l) => l.key === 'country')?.verdict, 'no', 'a company established outside the eligible countries is blocked');

const profile = (control: string, controlCountry: string) => parseProfile({ ...data.profiles.A3.stored, control, controlCountry });
const controlled = callFit(call, profile('other', 'cn'), null);
assert.equal(fitLabel(controlled).word, CONTROL_WORD);
assert.ok(!fitLabel(controlled).word.startsWith('Nothing known blocks you'));
assert.ok(fitLabel(controlled).detail.includes('guarantees approved by the eligible country'), 'the detail says the condition');
assert.equal(fitOrder(controlled, 0), 1, 'ranked with the other conditions that are no plain "check"');
assert.ok(fitLabel(callFit(call, profile('no', ''), null)).word.startsWith('Nothing known blocks you'), 'not controlled from elsewhere: unchanged');

console.log('wp137 checks passed');
