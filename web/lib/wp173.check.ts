/**
 * Self-check of WP-173: the funding findings of the QA of 24 November 2026 (D:\DEFENCEGATE TESTS\qa-full-nov24\c\REPORT-C.md).
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { check, countryStatus, sizeRule, type EligibilityFact, type EligibilityFacts } from './eligibility-check';
import { asksUaPartner, checkItems, conditionCount, fitLabel, type FitResult } from './fit';
import { budgetLabel, budgetScopeLine } from './format';
import { buildFundingAtom } from './funding-feed';
import { cutOffRow, lowerFirst, whatItFunds } from './funding-path';
import { generalHeadline } from './readiness';
import type { Call } from './types';

const fact = (value: unknown, quote = String(value), scope: EligibilityFact['scope'] = 'call_document'): EligibilityFact =>
  ({ value, quote, confidence: 0.9, scope });

// ---------------------------------------------------------------- C-1, C-9: every cut-off, every stage
const ref = new Date('2026-11-24T08:00:00Z');
assert.deepEqual(cutOffRow({ cutOffs: ['2027-02-25', '2027-09-16'], deadlineModel: 'two-stage' }, ref),
  { label: 'Stage deadlines', value: 'Stage 1: 25 Feb 2027; Stage 2: 16 Sep 2027' });
assert.deepEqual(cutOffRow({ cutOffs: ['2026-11-12', '2027-02-16', '2027-09-28'], deadlineModel: 'multiple cut-off' }, ref),
  { label: 'All cut-offs', value: '12 Nov 2026 (passed); 16 Feb 2027; 28 Sep 2027' });
assert.equal(cutOffRow({ cutOffs: ['2027-02-25'], deadlineModel: 'single-stage' }, ref), null);
assert.equal(cutOffRow({}, ref), null);

// ---------------------------------------------------------------- F13: "What it funds" does not repeat the title
assert.equal(whatItFunds({ title: 'Key electronic components', scope: ['Semiconductors'], actionType: null }), 'The source’s keywords for this topic: Semiconductors.');

// ---------------------------------------------------------------- F03, F14, A-8, C-8: one budget label everywhere
assert.equal(budgetLabel({ budgetScope: 'call', programme: 'EDIP' }), 'Call budget, all topics');
assert.equal(budgetLabel({ budgetScope: 'call', programme: 'NATIONAL' }), 'Call budget');
assert.equal(budgetLabel({ budgetScope: 'topic', programme: 'EDF' }), 'Topic budget');
assert.equal(budgetLabel({ budgetScope: null }), 'Budget');
assert.equal(budgetScopeLine({ budgetScope: 'call', programme: 'NATIONAL' }), 'Budget of the whole call');
assert.equal(budgetScopeLine({ budgetScope: 'call', programme: 'HORIZON' }), 'Shared by all topics of the same call');
const feedCall = {
  id: '116', slug: '116-key-electronic-components', programme: 'EDIP', programmeName: 'European Defence Industry Programme', funder: 'European Commission',
  callId: 'EDF-EDIP-P-2026', topicId: 'EDF-EDIP-P-2026-KEC', title: 'Key electronic components', titleLanguage: 'en', originalTitle: null, originalLanguage: null,
  regime: 'defence', funderCountry: 'EU', issuer: null, status: 'open', openingDate: null, deadline: '2027-02-25T22:59:59Z', deadlineIsDate: true,
  budget: { amount: 282150000, currency: 'EUR' }, budgetScope: 'call', actionType: null, fundingRate: null, scope: [], eligibility: [],
  firstSeenAt: '2026-11-01T00:00:00Z', lastSeenAt: '2026-11-24T00:00:00Z', publishedAt: null,
  source: { sourceId: 'eu_portal', sourceName: 'EU Funding and Tenders Portal', url: 'https://ec.europa.eu/x', retrievedAt: '2026-11-24T00:00:00Z', licence: '', attribution: '' },
} as unknown as Call;
const atom = buildFundingAtom([feedCall], { origin: 'https://ci.example.test', query: '', describe: 'open calls', total: 1, generatedAt: '2026-11-24T00:00:00Z' });
assert.match(atom, /Call budget, all topics: EUR 282,150,000\./, 'A-8: the feed labels the EDIP budget');

// ---------------------------------------------------------------- C-5: EIC STEP Defence, the Union, Ukraine and the associated EEA members only
const step = fact('In accordance with Article 48(2) of the Horizon Europe Regulation, participation is limited to SMEs, including start-ups, and small mid-caps established in the Union, in Ukraine, or in an EEA member associated to Horizon Europe. This call has a general exclusion rule: legal entities that are directly or indirectly controlled by a third country other than Ukraine or an EEA member associated to Horizon Europe cannot participate.');
const ctx = { programme: 'HORIZON', topic: 'HORIZON-EIC-2027-DEFENCE-01' };
for (const c of ['US', 'GB', 'CH', 'TR', 'IL']) assert.equal(countryStatus(step, c, ctx).verdict, 'no', `C-5 ${c}`);
assert.equal(countryStatus(step, 'NO', ctx).verdict, 'yes', 'C-5 NO: an EEA member associated');
assert.equal(countryStatus(step, 'LI', ctx).verdict, 'no', 'C-5 LI: not associated to Horizon Europe');
assert.equal(countryStatus(step, 'UA', ctx).verdict, 'yes', 'C-5 UA: named');
assert.equal(countryStatus(step, 'PL', ctx).verdict, 'yes');
// a list that opens to every associated country is unchanged
assert.equal(countryStatus(fact('Member States and countries associated to Horizon Europe'), 'CH', ctx).verdict, 'yes');
// the size limit inside the country sentence
assert.equal(sizeRule({ eligible_countries: step })?.limit, 499);
const large = check({ eligible_countries: step }, { country: 'PL', orgType: 'large', hasPartners: '', controlledAbroad: '' }, ctx);
assert.equal(large.lines.find((l) => l.key === 'sme')?.verdict, 'check', 'C-5: a large company is not "nothing blocks you"');
assert.match(large.lines.find((l) => l.key === 'sme')!.reason, /SMEs and small mid-caps \(up to 499 staff\)/);

// ---------------------------------------------------------------- C-6: natural persons, two blockers named, no irrelevant question
const usi: EligibilityFacts = {
  natural_persons_allowed: { ...fact(false, 'Natural persons are NOT eligible (with the exception of self-employed persons, i.e. sole traders, where the company does not have legal personality separate from that of the natural person).'), note: 'Exception: self-employed persons (sole traders) may apply.' },
  eligible_countries: fact('EU Member States (including overseas countries and territories (OCTs)); Ukraine'),
};
const person = check(usi, { country: 'UA', orgType: 'individual', hasPartners: '', controlledAbroad: '' });
assert.equal(person.lines.find((l) => l.key === 'person')?.verdict, 'no', 'C-6: a natural person is blocked');
assert.match(person.lines.find((l) => l.key === 'person')!.reason, /answer as a small or medium enterprise/);
const two: FitResult = { fit: 'no', result: null, conditions: [], blockedBy: ['Country', 'Partners'] };
assert.equal(fitLabel(two).word, 'Blocked by: Country and Partners', 'C-6: the second blocker is named');
assert.equal(fitLabel({ ...two, blockedBy: ['a', 'b', 'c'] }).word, 'Blocked by: a and 2 more');
const uaRules = { regime: { code: 'EDIP-USI', name: 'USI' }, byCountry: { EU: [{ rule: 'USI-UA-PARTNER', title: 't', outcome: 'unknown', reason: '', asks: ['ua_partner'] }], OTHER: [{ rule: 'USI-UA-PARTNER', title: 't', outcome: 'unknown', reason: '', asks: ['ua_partner'] }] } } as unknown as Call['rulesApply'];
assert.equal(asksUaPartner({ rulesApply: uaRules }, 'PL', usi), true);
assert.equal(asksUaPartner({ rulesApply: uaRules }, 'US', usi), false, 'C-6: not asked of a country the call excludes');

// ---------------------------------------------------------------- F12: "N conditions" lists those N
const r: FitResult = { fit: 'yes', result: { verdict: 'check', lines: [
  { key: 'country', label: 'Country', verdict: 'check', reason: 'a' }, { key: 'sme', label: 'Size', verdict: 'yes', reason: 'b' },
] }, conditions: ['c'], blockedBy: [] };
assert.equal(conditionCount(r), 2);
assert.deepEqual(checkItems(r).map((i) => i.key), ['country', 'condition-0']);
assert.equal(fitLabel(r).word, 'Nothing known blocks you, 2 conditions to check');

// ---------------------------------------------------------------- C-11: not "nothing to do" above rules that apply
assert.equal(generalHeadline([{ title: 'X', outcome: 'met' }]), 'Nothing to do under these rules on the answers given.');
assert.equal(generalHeadline([{ title: 'Facility security clearance (other countries)', outcome: 'info' }, { title: 'Certified recipient', outcome: 'conditional' }]),
  'Nothing required on the answers given. To read, as they apply to you: Facility security clearance (other countries); Certified recipient.');

// ---------------------------------------------------------------- C-14: "EEA" stays capitalised
assert.equal(lowerFirst('EEA countries are eligible under this call.'), 'EEA countries are eligible under this call.');
assert.equal(lowerFirst('Your country is named'), 'your country is named');

console.log('wp173 checks passed');
