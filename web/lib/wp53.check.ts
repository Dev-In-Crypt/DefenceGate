/**
 * Self-check of WP-53 (readiness correctness, 19 October 2026). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 *
 *   T7   the headline of the roadmap is computed from the cost data of the steps;
 *   T21  the partner questions: a condition on who applies with whom that the saved profile answers, on the stored facts of the
 *        nine open EDF/EDIP calls of 19 October 2026 (`data/wp53-edip-calls.json`, read from the public call pages: the facts, the
 *        notes and a shortened quote, no personal data).
 * The profile (T4 to T6) is in profile.check.ts, the rule engine in backend/tests/unit/test_wp53_readiness.py.
 */
import assert from 'node:assert/strict';
import calls from './data/wp53-edip-calls.json';
import { check, countryNote, entityNote, partnerKind, partnerLine, partnerNeeds, type EligibilityFacts, type Profile as CheckProfile } from './eligibility-check';
import { applicantFit, checkProfileOf, fitOf, shownFit, withProgramme } from './fit';
import { emptyProfile, type Profile } from './profile';
import { costHeadline, timeHeadline } from './readiness';
import type { RoadmapTotals } from './readiness-types';

// ------------------------------------------------------------------ T7: the headline of the roadmap

const totals = (cost: RoadmapTotals['cost'], freeSteps: string[]): RoadmapTotals => ({ cost, freeSteps, days: { min: 5, max: 20 } });
const eur = [{ currency: 'EUR', min: 100, max: 200, steps: ['C'] }];

assert.equal(costHeadline(totals([], ['A', 'B']), 2, 0), 'Free', 'free only when every step states that it is free');
// the case of the audit: four steps, two free, two with no stated cost; the headline said "Free"
assert.equal(costHeadline(totals([], ['A', 'B']), 4, 2), '2 steps free, 2 with no stated cost');
assert.equal(costHeadline(totals([], ['A']), 3, 2), '1 step free, 2 with no stated cost');
assert.equal(costHeadline(totals([], []), 2, 2), '2 steps with no stated cost');
assert.equal(costHeadline(totals([], []), 1, 1), '1 step with no stated cost');
assert.equal(costHeadline(totals(eur, []), 1, 0), 'EUR 100 to 200');
assert.equal(costHeadline(totals(eur, []), 2, 1), 'EUR 100 to 200, 1 step with no stated cost', 'a sum of some steps is not the cost of the plan');
assert.equal(costHeadline(totals(eur, ['A']), 3, 1), 'EUR 100 to 200, 1 step free, 1 with no stated cost');
assert.equal(costHeadline(totals(eur, ['A']), 2, 0), 'EUR 100 to 200');
assert.equal(costHeadline(totals([], []), 0, 0), 'Nothing is stated');
assert.ok(!/free/i.test(costHeadline(totals([], []), 2, 2)), 'nothing stated is not free');

assert.equal(timeHeadline({ min: 5, max: 20 }, 4, 0), '5 to 20 days');
assert.equal(timeHeadline({ min: 5, max: 20 }, 4, 2), '5 to 20 days, 2 with no stated time');
assert.equal(timeHeadline({ min: 0, max: 0 }, 2, 2), '2 steps with no stated time', 'unknown time is not "no time needed"');
assert.equal(timeHeadline({ min: 0, max: 0 }, 2, 0), 'no time needed');

// ------------------------------------------------------------------ T21: the sentences

assert.equal(partnerKind('A single applicant must be a legal entity established and having its executive management structure in Ukraine.'), 'ukraine');
assert.equal(partnerKind('The single applicant must be established and have its executive management structure in Ukraine.'), 'ukraine');
assert.equal(partnerKind('consortia must include at least one legal entity established and having its executive management structures in Ukraine.'), 'ukraine');
assert.equal(partnerKind('For proposals including activities within the meaning of Article 12(1)(d) of the EDIP Regulation, a single applicant cannot apply unless a SEAP participates.'), 'seap');
assert.equal(partnerKind('Not for actions within Article 12(1)(d) of the EDIP Regulation when no SEAP participates.'), 'seap');
assert.equal(partnerKind('This is the minimum for the topic;'), 'harmless');
assert.equal(partnerKind('Only a SEAP may apply as a single applicant; it must meet the stated minimum country composition.'), 'other', 'the applicant is a SEAP: not a partner');
assert.equal(partnerKind('Legal entities established in the non-government controlled areas of Ukraine are not eligible for funding.'), 'other');

type Fact = { value: unknown; note: string | null; quote: string; confidence: number; scope?: 'call_document' | 'general' | 'topic' };
const factsOf = (id: number): EligibilityFacts => (calls as unknown as Record<string, { topic: string; facts: Record<string, Fact> }>)[String(id)].facts;
const topicOf = (id: number): string => (calls as unknown as Record<string, { topic: string }>)[String(id)].topic;

const needs = (id: number) => partnerNeeds(factsOf(id));
assert.deepEqual(needs(118), { ukraine: true, seap: true, other: false });
assert.deepEqual(needs(113), { ukraine: true, seap: false, other: false });
assert.deepEqual(needs(116), { ukraine: false, seap: true, other: false });
assert.deepEqual(needs(117), { ukraine: false, seap: true, other: false });
for (const id of [114, 193, 110, 111, 112]) assert.equal(needs(id).other, true, `${id}: a condition about the applicant itself is not a partner condition`);

// ------------------------------------------------------------------ T21: a company that meets every stated condition

const company = (over: Partial<Profile> = {}): Profile => ({
  ...emptyProfile(), step: 6, country: 'PL', sizeClass: 'small', legalForm: 'legal_person', applicantKind: 'company_or_research', management: 'same',
  control: 'no', uaPartner: 'yes', seapPartner: 'yes', ...over,
});
const IDS = [118, 114, 193, 110, 111, 112, 113, 116, 117];
/** The document's verdict and the applicant rule of the topic, as the call page shows them before the programme's assessment (which the API computes). */
const shown = (id: number, p: Profile) => shownFit(withProgramme(fitOf(factsOf(id), p), applicantFit('EDF', topicOf(id), p)));
const yes = (p: Profile) => IDS.filter((id) => shown(id, p) === 'yes');

// before this package no call could be a yes (the profile had no answer about partners); now four can, and they are the four open to a company
assert.deepEqual(yes(company()), [118, 113, 116, 117]);
for (const id of [114, 193, 110, 111, 112]) assert.equal(shown(id, company()), 'no', `${id} is open to contracting authorities and SEAPs, not to a company`);

// each answer matters, and an answer that is missing leaves the line a check, never a no
assert.equal(shown(118, company({ uaPartner: '' })), 'check');
assert.equal(shown(118, company({ seapPartner: '' })), 'check', 'call 118 also asks for a SEAP or three independent entities');
assert.equal(shown(118, company({ uaPartner: 'no' })), 'check');
assert.equal(shown(118, company({ uaPartner: 'unsure' })), 'check');
assert.equal(shown(113, company({ seapPartner: '' })), 'yes', 'call 113 asks only for the Ukrainian entity');
assert.equal(shown(113, company({ uaPartner: '' })), 'check');
assert.equal(shown(116, company({ uaPartner: '' })), 'yes', 'calls 116 and 117 do not ask for a Ukrainian entity');
assert.equal(shown(116, company({ seapPartner: '' })), 'check');
assert.equal(shown(116, company({ seapPartner: 'no' })), 'check');
assert.equal(shown(117, company({ seapPartner: 'unsure' })), 'check');
const ua118 = fitOf(factsOf(118), company({ uaPartner: 'no' })).result!.lines.find((l) => l.key === 'consortium')!;
assert.match(ua118.reason, /You said no legal entity established in Ukraine takes part in your consortium\./);
assert.match(ua118.reason, /A single applicant may apply under a condition/, 'the call\'s own condition is still printed');
const seap116 = fitOf(factsOf(116), company({ seapPartner: '' })).result!.lines.find((l) => l.key === 'consortium')!;
assert.match(seap116.reason, /Your answers do not say whether a SEAP takes part in your consortium\./);
const met116 = fitOf(factsOf(116), company()).result!.lines.find((l) => l.key === 'consortium')!;
assert.equal(met116.verdict, 'yes');
assert.match(met116.reason, /your answers meet them: you said a SEAP takes part in your consortium\./);
// no partner answer ever excludes
for (const id of IDS) for (const a of ['', 'no', 'unsure'] as const) assert.notEqual(fitOf(factsOf(id), company({ uaPartner: a, seapPartner: a })).fit, 'no', `${id} ${a}`);

// the other lines that used to keep a yes out of reach: notes about kinds of applicant the profile is not, and the Ukrainian areas
const line = (id: number, key: string, p: Profile = company()) => fitOf(factsOf(id), p).result!.lines.find((l) => l.key === key)!;
assert.equal(line(118, 'entity').verdict, 'yes');
assert.equal(line(116, 'entity').verdict, 'yes');
assert.equal(line(117, 'entity').verdict, 'yes');
assert.equal(line(118, 'country').verdict, 'yes', 'the non-government controlled areas of Ukraine do not concern a company in Poland');
assert.equal(line(113, 'country').verdict, 'yes');
assert.equal(line(117, 'country').verdict, 'yes', 'executive management in the company\'s own country, which the call names');
// ... and only for a profile that answers what the note is about
assert.equal(line(118, 'entity', company({ legalForm: '' })).verdict, 'check', 'a legal form that was not answered: the note about entities without legal personality stays');
assert.equal(line(118, 'entity', company({ applicantKind: '' })).verdict, 'check', 'a kind that was not answered: the note about international organisations stays');
assert.equal(line(116, 'entity', company({ applicantKind: 'seap' })).verdict, 'check');
assert.equal(line(117, 'country', company({ management: '' })).verdict, 'check', 'executive management not answered');
assert.equal(line(117, 'country', company({ management: 'other', managementCountry: 'CH' })).verdict, 'check', 'executive management in a country the call does not name');
assert.equal(line(117, 'country', company({ management: 'other', managementCountry: 'NO' })).verdict, 'yes', 'in an EEA country, which the call names');
const ukCountries = factsOf(113).eligible_countries;
assert.equal(line(113, 'country', company({ country: 'UA', uaOccupied: 'no' })).verdict, 'yes', 'WP-93: the call names Ukraine, so a Ukrainian company is eligible on the country (it was a check)');
assert.equal(countryNote(ukCountries, 'UA', checkProfileOf(company({ country: 'UA', uaOccupied: 'no' }))!.more), '', 'but the note about the areas is answered');
assert.match(countryNote(ukCountries, 'UA', checkProfileOf(company({ country: 'UA', uaOccupied: '' }))!.more), /non-government/, 'a Ukrainian company that did not answer keeps the note');
assert.match(countryNote(ukCountries, 'UA', checkProfileOf(company({ country: 'UA', uaOccupied: 'yes' }))!.more), /non-government/);
assert.equal(countryNote(ukCountries, 'PL', checkProfileOf(company())!.more), '');
assert.match(countryNote(ukCountries, '', checkProfileOf(company())!.more), /non-government/, 'no country chosen: nothing is settled');

// a Ukrainian company is the Ukrainian entity itself
const uaCompany = company({ country: 'UA', uaPartner: '', uaOccupied: 'no', seapPartner: 'yes' });
assert.equal(fitOf(factsOf(113), uaCompany).result!.lines.find((l) => l.key === 'consortium')!.verdict, 'yes');
assert.match(fitOf(factsOf(113), uaCompany).result!.lines.find((l) => l.key === 'consortium')!.reason, /your company is established in Ukraine, with its executive management there/);
const uaElsewhere = company({ country: 'UA', uaPartner: '', uaOccupied: 'no', management: 'other', managementCountry: 'CH' });
assert.equal(fitOf(factsOf(113), uaElsewhere).result!.lines.find((l) => l.key === 'consortium')!.verdict, 'check', 'its executive management is not in Ukraine');
assert.match(fitOf(factsOf(113), uaElsewhere).result!.lines.find((l) => l.key === 'consortium')!.reason, /do not place your executive management in Ukraine/);
assert.equal(fitOf(factsOf(113), company({ country: 'UA', uaPartner: '', uaOccupied: 'no', management: '' })).result!.lines.find((l) => l.key === 'consortium')!.verdict, 'check');

// ------------------------------------------------------------------ T21: what the profile leaves out stays as before

// the form of the call page has no such answers: every line reads as before
const form: CheckProfile = { country: 'PL', orgType: 'sme', hasPartners: '', controlledAbroad: 'no' };
assert.equal(partnerLine(factsOf(113), form)!.verdict, 'check');
assert.equal(partnerLine(factsOf(116), form)!.verdict, 'check');
assert.equal(check(factsOf(118), form).lines.find((l) => l.key === 'entity')!.verdict, 'check');
assert.equal(check(factsOf(113), form).lines.find((l) => l.key === 'country')!.verdict, 'check');
assert.equal(entityNote(factsOf(118).entity_types, undefined), factsOf(118).entity_types!.note);
assert.equal(countryNote(factsOf(113).eligible_countries, 'PL', undefined), factsOf(113).eligible_countries!.note);
// a call with no note on the consortium or the single applicant has no such line at all
assert.equal(partnerLine({ consortium_required: { value: false, note: null, quote: 'q', confidence: 1 } }, form), null);
// a note the profile cannot answer keeps the call a check whatever the partner answers say
const other = { ...factsOf(113), consortium_required: { value: true, note: 'Applicants must also submit a letter of support from the ministry.', quote: 'q', confidence: 1 } };
assert.equal(partnerLine(other, checkProfileOf(company())!)!.verdict, 'check');
assert.equal(partnerNeeds(other).other, true);
// the checked profile carries the answers
assert.deepEqual(checkProfileOf(company())!.more, { legalPerson: true, company: true, managementCountry: 'PL', uaOccupied: '', uaPartner: 'yes', seapPartner: 'yes' });
assert.equal(checkProfileOf(company({ management: '' }))!.more!.managementCountry, '');

console.log('wp53.check ok');
