/**
 * Self-check of the fit of a call to the saved profile (WP-32, 17 October 2026). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import type { EligibilityFacts } from './eligibility-check';
import { checkProfileOf, fitOf, fitsProfile, programmeFit, programmesOfCall, withProgramme } from './fit';
import { emptyProfile, type Profile } from './profile';
import type { ProgrammeAssessment, RoadmapStep } from './readiness-types';

const f = (value: unknown, note: string | null = null, scope: 'call_document' | 'general' | 'topic' = 'call_document') =>
  ({ value, note, quote: 'q', confidence: 1, scope });
const profile = (over: Partial<Profile>): Profile => ({ ...emptyProfile(), step: 6, ...over });
const UA = profile({ country: 'UA', sizeClass: 'small', control: 'no' });
const ES = profile({ country: 'ES', sizeClass: 'small', control: 'no' });
const LARGE_ES = profile({ country: 'ES', sizeClass: 'large', control: 'no' });

// The profile of the readiness check, as the form of the call page reads it.
assert.equal(checkProfileOf(profile({})), null, 'no country, no verdict');
assert.deepEqual(checkProfileOf(ES), { country: 'ES', orgType: 'sme', hasPartners: '', controlledAbroad: 'no' });
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

// A consortium call: the requirement is the same for every applicant, so it does not decide the verdict, but it always
// comes with it as a condition, because the profile does not say whether the company has partners.
const consortium: EligibilityFacts = { ...single, consortium_required: f(true), min_entities: f(3), min_countries: f(3) };
assert.equal(fitOf(consortium, ES).fit, 'yes');
assert.deepEqual(fitOf(consortium, ES).conditions.length, 1);
assert.match(fitOf(consortium, ES).conditions[0], /at least 3 legal entities from at least 3 countries.*does not say whether you have partners/);
assert.deepEqual(fitOf(single, ES).conditions, [], 'no consortium, no condition');
assert.equal(fitOf(consortium, UA).fit, 'check', 'the condition does not hide a rule that needs a look');
assert.equal(fitOf(consortium, LARGE_ES).fit, 'yes');
assert.equal(fitOf({ ...consortium, sme_only: f(true) }, LARGE_ES).fit, 'no', 'and does not hide a rule that excludes');

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
assert.deepEqual(rows, [['yes', 'check'], ['yes', 'check'], ['yes', 'check'], ['yes', 'check'], ['check', 'check']]);

// ---- the programme's rules: which programme judges a call, and what its verdict does to the badge
assert.deepEqual(programmesOfCall('EDF', 'EDF-2026-DA-SPACE-PRS-STEP'), ['EDF']);
assert.deepEqual(programmesOfCall('EDF', 'EDF-EDIP-P-2027-FNLC-CPA-AMDS'), ['EDIP'], 'filed under the EDF, judged by the EDIP');
assert.deepEqual(programmesOfCall('EDF', 'EDF-EDIP-USI-2027-LS-IRA-CUXS'), ['EDIP-USI']);
assert.deepEqual(programmesOfCall('EDIP', 'EDIP-2026-RAMPUP-COMP'), ['EDIP', 'EDIP-USI'], 'a code that says neither gets both');
assert.deepEqual(programmesOfCall('HORIZON', 'HORIZON-CL3-2026-01-BM-01'), []);
assert.deepEqual(programmesOfCall('NATIONAL', 'PL-NCBR-1'), []);

const rule = (code: string, requirement: string | null, title: string) => ({ rule: code, title, outcome: 'not_met', reason: '', obligation: 'mandatory', kind: '', requirement, note: null, denominator: null, asks: [], source: {} });
const programme = (code: string, name: string, verdict: string, blocking: string[], rules: ReturnType<typeof rule>[]) =>
  ({ programme: code, name, kind: 'programme', summary: '', legalBasis: null, sourceUrl: '', verdict, incomplete: false, blocking, conditions: [], counts: {}, missing: [], rules } as unknown as ProgrammeAssessment);
const step = (code: string, name: string, blockingFor: string[]) => ({ order: 1, code, name, blockingFor } as unknown as RoadmapStep);
const EDIP_UA = programme('EDIP', 'EDIP', 'blocked', ['EDIP-ESTABLISH', 'EDIP-PIC'], [rule('EDIP-ESTABLISH', null, 'Established in the Union or an associated country'), rule('EDIP-PIC', 'REQ-PIC', 'PIC')]);
const USI_UA = programme('EDIP-USI', 'EDIP Ukraine Support Instrument', 'blocked', ['USI-PIC'], [rule('USI-PIC', 'REQ-PIC', 'PIC')]);
const EDF_ES = programme('EDF', 'EDF', 'eligible', [], []);
const EDF_OPEN = programme('EDF', 'EDF', 'conditional', [], []);
const pic = step('REQ-PIC', 'Participant Identification Code', ['EDIP', 'EDIP-USI', 'EDF']);
const ua = { assessments: [EDIP_UA, USI_UA, EDF_ES], roadmap: { steps: [pic] } } as never;

const noEdip = programmeFit(ua, ['EDIP'])!;
assert.equal(noEdip.fit, 'no', 'a rule that no certificate fixes');
assert.deepEqual(noEdip.because, ['EDIP: Established in the Union or an associated country']);
const usi = programmeFit(ua, ['EDIP-USI'])!;
assert.deepEqual([usi.fit, usi.because], ['check', ['Needs first: Participant Identification Code']], 'only the PIC is missing');
assert.equal(programmeFit(ua, ['EDIP', 'EDIP-USI'])!.fit, 'check', 'a call that may belong to either part: the better one counts');
assert.equal(programmeFit(ua, ['EDF'])!.fit, 'yes');
assert.equal(programmeFit({ assessments: [EDF_OPEN], roadmap: { steps: [] } } as never, ['EDF'])!.fit, 'check');
assert.equal(programmeFit(null, ['EDF']), null, 'no verdict asked or none came');
assert.equal(programmeFit(ua, []), null, 'a programme with no rules');
assert.equal(programmeFit(ua, ['SAFE']), null);

const docYes = fitOf(single, ES);
const docUnknown = fitOf(null, ES);
assert.equal(withProgramme(docYes, noEdip).fit, 'no');
assert.equal(withProgramme(docUnknown, noEdip).fit, 'no', 'a call whose rules were not read is still out of reach of a company the programme excludes');
assert.deepEqual(withProgramme(docUnknown, usi).fit, 'unknown', 'but "something must be obtained" says nothing of a call whose rules were not read');
assert.equal(withProgramme(docYes, usi).fit, 'check');
assert.equal(withProgramme(fitOf(restricted, ES), programmeFit(ua, ['EDF'])).fit, 'yes');
assert.equal(withProgramme(fitOf(single, UA), programmeFit(ua, ['EDF'])).fit, 'check');
assert.equal(withProgramme(fitOf(smeOnly, LARGE_ES), usi).fit, 'no', 'the document excludes: the programme cannot lift it');
assert.equal(withProgramme(docYes, null), docYes);
assert.ok(withProgramme(docYes, usi).conditions[0].startsWith('Needs first'));
console.log('fit checks passed');
