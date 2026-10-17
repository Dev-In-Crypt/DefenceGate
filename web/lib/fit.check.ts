/**
 * Self-check of the fit of a call to the saved profile (WP-32, 17 October 2026). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import type { EligibilityFacts } from './eligibility-check';
import { checkProfileOf, fitOf, fitsProfile } from './fit';
import { emptyProfile, type Profile } from './profile';

const f = (value: unknown, note: string | null = null, scope: 'call_document' | 'general' | 'topic' = 'call_document') =>
  ({ value, note, quote: 'q', confidence: 1, scope });
const profile = (over: Partial<Profile>): Profile => ({ ...emptyProfile(), step: 6, ...over });
const UA = profile({ country: 'UA', sizeClass: 'small', control: 'no' });
const ES = profile({ country: 'ES', sizeClass: 'small', control: 'no' });
const LARGE_ES = profile({ country: 'ES', sizeClass: 'large', control: 'no' });

// The profile of the readiness check, as the form of the call page reads it.
assert.equal(checkProfileOf(profile({})), null, 'no country, no verdict');
assert.deepEqual(checkProfileOf(ES), { country: 'ES', orgType: 'sme', hasPartners: 'unsure', controlledAbroad: 'no' });
assert.equal(checkProfileOf(LARGE_ES)!.orgType, 'large');
assert.equal(checkProfileOf(profile({ country: 'ES' }))!.orgType, '');
assert.equal(checkProfileOf(profile({ country: 'ES', control: 'other' }))!.controlledAbroad, 'yes');
assert.equal(checkProfileOf(profile({ country: 'ES', control: 'ua_eea_only' }))!.controlledAbroad, 'unsure');
assert.equal(checkProfileOf(profile({ country: 'ES', control: '' }))!.controlledAbroad, 'unsure');

// A call that needs no consortium and has no restriction: an EU company is eligible, a Ukrainian one must check.
const single: EligibilityFacts = {
  eligible_countries: f('Legal entities established in EU Member States'),
  consortium_required: f(false), sme_only: f(false), ownership_control_restriction: f(false),
};
assert.equal(fitOf(single, ES).fit, 'yes');
assert.equal(fitOf(single, UA).fit, 'check', 'Ukraine is not a Member State: the document decides');

// A consortium call is never a plain yes: the profile does not say whether the company has partners.
const consortium: EligibilityFacts = { ...single, consortium_required: f(true), min_entities: f(3), min_countries: f(3) };
assert.equal(fitOf(consortium, ES).fit, 'check');
assert.match(fitOf(consortium, ES).result!.lines.find((l) => l.key === 'consortium')!.reason, /at least 3 legal entities from at least 3 countries/);

// A restriction on ownership control is a yes only when the profile says "not controlled from outside".
const restricted: EligibilityFacts = { ...single, ownership_control_restriction: f(true) };
assert.equal(fitOf(restricted, ES).fit, 'yes');
assert.equal(fitOf(restricted, profile({ country: 'ES', sizeClass: 'small', control: 'other' })).fit, 'no');
assert.equal(fitOf(restricted, profile({ country: 'ES', sizeClass: 'small', control: '' })).fit, 'check');
assert.equal(fitOf(restricted, profile({ country: 'ES', sizeClass: 'small', control: 'ua_eea_only' })).fit, 'check');

// SMEs only: a large company is out, a small one is in, an unanswered size is a check.
const smeOnly: EligibilityFacts = { ...single, sme_only: f(true) };
assert.equal(fitOf(smeOnly, LARGE_ES).fit, 'no');
assert.equal(fitOf(smeOnly, ES).fit, 'yes');
assert.equal(fitOf(smeOnly, profile({ country: 'ES', control: 'no' })).fit, 'check');

// A condition in a note turns a yes into a check.
assert.equal(fitOf({ ...single, sme_only: f(false, 'a bonus for SMEs') }, ES).fit, 'check');

// A rule that comes from the work programme's general annexes is never a plain yes and never a firm no.
const general: EligibilityFacts = {
  eligible_countries: f('Legal entities established in EU Member States', null, 'general'), consortium_required: f(false, null, 'general'),
};
assert.equal(fitOf(general, ES).fit, 'check');
assert.match(fitOf(general, ES).result!.lines[0].reason, /general rule/);
assert.equal(fitOf({ sme_only: f(true, null, 'general') }, LARGE_ES).fit, 'check');
// The same facts read from the topic's own text count in full.
assert.equal(fitOf({ sme_only: f(true, null, 'topic') }, LARGE_ES).fit, 'no');

// Nothing to compare: unknown, never yes.
assert.equal(fitOf(null, ES).fit, 'unknown');
assert.equal(fitOf(undefined, ES).fit, 'unknown');
assert.equal(fitOf({}, ES).fit, 'unknown');
assert.equal(fitOf({ funding_rate: f('70 %') }, ES).fit, 'unknown', 'a fact the profile cannot be compared with');
assert.equal(fitOf(single, null).fit, 'unknown');
assert.equal(fitOf(single, profile({})).fit, 'unknown');

// The filter keeps what is eligible or worth a look, and nothing undecided.
assert.deepEqual((['yes', 'check', 'no', 'unknown', undefined] as const).map(fitsProfile), [true, true, false, false, false]);

// The two profiles of the acceptance test see different verdicts on the same calls.
const rows = [single, consortium, restricted, smeOnly, general].map((facts) => [fitOf(facts, ES).fit, fitOf(facts, UA).fit]);
assert.deepEqual(rows, [['yes', 'check'], ['check', 'check'], ['yes', 'check'], ['yes', 'check'], ['check', 'check']]);
console.log('fit checks passed');
