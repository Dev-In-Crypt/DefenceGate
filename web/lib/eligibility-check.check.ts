/**
 * Self-check of the "Can you apply?" verdict (WP-25, 17 October 2026). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { check, type EligibilityFacts, type Profile } from './eligibility-check';

const f = (value: unknown, note: string | null = null) => ({ value, note, quote: 'q', confidence: 1 });
const edf: EligibilityFacts = {
  eligible_countries: f('EU Member States, listed EEA countries and associated countries'),
  sme_only: f(false),
  natural_persons_allowed: f(false, 'sole traders are an exception'),
  consortium_required: f(true),
  min_entities: f(3),
  min_countries: f(3),
  ownership_control_restriction: f(true),
};
const base: Profile = { country: 'ES', orgType: 'sme', hasPartners: 'yes', controlledAbroad: 'no' };

// Everything allows it, nothing carries a condition: yes.
assert.equal(check(edf, base).verdict, 'yes');
// Without partners the verdict is "check", never "no".
assert.equal(check(edf, { ...base, hasPartners: 'no' }).verdict, 'check');
// Controlled from outside the eligible countries: no.
assert.equal(check(edf, { ...base, controlledAbroad: 'yes' }).verdict, 'no');
assert.equal(check(edf, { ...base, controlledAbroad: 'unsure' }).verdict, 'check');
// A country outside the EU is "check": the associated-country list is in the document.
assert.equal(check(edf, { ...base, country: 'UA' }).verdict, 'check');
assert.equal(check(edf, { ...base, country: 'NO' }).verdict, 'yes');
// A natural person: the exception in the note makes it "check", not "no".
assert.equal(check(edf, { ...base, orgType: 'individual' }).verdict, 'check');
assert.equal(check({ ...edf, natural_persons_allowed: f(false) }, { ...base, orgType: 'individual' }).verdict, 'no');
// SME-only call and a large company: no.
assert.equal(check({ ...edf, sme_only: f(true) }, { ...base, orgType: 'large' }).verdict, 'no');
// A condition in a note turns a plain yes into "check".
assert.equal(check({ ...edf, sme_only: f(false, 'a bonus for SMEs only') }, base).verdict, 'check');
// A fact that was not read adds no line; with nothing to compare the result is yes with no lines.
const none = check({}, base);
assert.deepEqual([none.verdict, none.lines.length], ['yes', 0]);
// Unanswered questions add no line.
assert.equal(check(edf, { country: '', orgType: '', hasPartners: '', controlledAbroad: '' }).lines.length, 0);
// WP-31: a fact read from the work programme's general annexes is never a "no"; the topic may change it.
const general = (value: unknown, note: string | null = null) => ({ value, note, quote: 'q', confidence: 1, scope: 'general' as const });
const fromAnnexes: EligibilityFacts = { ...edf, sme_only: general(true), ownership_control_restriction: general(true) };
assert.equal(check(fromAnnexes, { ...base, orgType: 'large' }).verdict, 'check');
assert.equal(check(fromAnnexes, { ...base, controlledAbroad: 'yes' }).verdict, 'check');
assert.match(check(fromAnnexes, { ...base, controlledAbroad: 'yes' }).lines.find((l) => l.key === 'control')!.reason, /general rule/);
// ...while the same fact read from the topic's own text, or from a call document, still is.
const topic = { ...fromAnnexes, sme_only: { ...fromAnnexes.sme_only!, scope: 'topic' as const } };
assert.equal(check(topic, { ...base, orgType: 'large' }).verdict, 'no');
console.log('eligibility-check checks passed');
