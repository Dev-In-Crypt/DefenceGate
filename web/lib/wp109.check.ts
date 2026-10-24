/**
 * Self-check of WP-109 (round 4 of 24 October 2026): one verdict per call page, the Fits order, the funding list and its exports.
 * The calls are what production served on 24 October (data/wp109-calls.json). Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import type { EligibilityFacts } from './eligibility-check';
import { NATIONALITY_PREFIX, NO_UA_PARTNER, answersFit, answersOf, asksUaPartner, callFit, fitLabel, fitOrder, shownFit, verdictLines, type Answers, type PageCall } from './fit';
import { applySummary, otherTopicCode } from './funding-path';
import { buildFundingAtom, programmeNameOf } from './funding-feed';
import { emptyProfile, type Profile } from './profile';
import type { Call, RulesApply } from './types';

const data = JSON.parse(readFileSync('lib/data/wp109-calls.json', 'utf8'));
type Raw = { id: string; programme: string; topicId: string; title: string; facts: EligibilityFacts; rulesApply: RulesApply | null };
const raw = (id: string): Raw => data.calls[id];
const page = (id: string): PageCall => ({ facts: raw(id).facts, programme: raw(id).programme, topic: raw(id).topicId, rulesApply: raw(id).rulesApply });
const ask = (a: Partial<Answers>): Answers => ({ country: '', orgType: '', hasPartners: '', controlledAbroad: '', ...a });
const verdictOf = (id: string, a: Partial<Answers>) => shownFit(answersFit(page(id), ask(a)));
const asCall = (id: string) => ({ ...raw(id), documentEligibility: { documentUrl: null, extractedAt: '', facts: raw(id).facts } }) as unknown as Call;

// ---------------------------------------------------------------- 1. one verdict per call page, without a saved profile

// SEAP 114: the top said "cannot apply", the bare form "none is a no" for an SME, a large company and a university
for (const orgType of ['sme', 'large', 'university'] as const) {
  const r = answersFit(page('114'), ask({ country: 'BE', orgType }));
  assert.equal(shownFit(r), 'no', `114 ${orgType}`);
  assert.ok(verdictLines(r).some((l) => l.key === 'who' && l.verdict === 'no'));
  // the first screen's own lines say the same: companies cannot apply
  assert.equal(applySummary(asCall('114'), 'BE', 'company_or_research')!.verdict, 'no');
}
assert.equal(verdictOf('114', { country: 'BE', orgType: 'public' }), 'check');     // a SEAP answers "public body": a check, not a no

// USI 118: the Ukrainian-partner rule is in the form too
assert.equal(asksUaPartner(page('118'), 'PL'), true);
assert.equal(asksUaPartner(page('118'), 'UA'), false);
const pl = answersFit(page('118'), ask({ country: 'PL', orgType: 'sme' }));
assert.equal(shownFit(pl), 'check');
assert.ok(pl.result!.lines.some((l) => l.key === 'ua-partner' && /partner established in Ukraine/.test(l.reason)));
const none = answersFit(page('118'), ask({ country: 'PL', orgType: 'sme', uaPartner: 'no' }));
assert.equal(fitLabel(none).word, NO_UA_PARTNER);
assert.equal(verdictOf('118', { country: 'US', orgType: 'sme' }), 'no');          // established outside the Union and Ukraine
assert.equal(applySummary(asCall('118'), 'US')!.verdict, 'no');

// EIC 131: a university and a group of 2,000 staff are a no on the top and in the form alike; an SME is not
assert.equal(verdictOf('131', { country: 'BE', orgType: 'university' }), 'no');
assert.equal(verdictOf('131', { country: 'BE', orgType: 'large', headcount: '2000plus' }), 'no');
assert.equal(verdictOf('131', { country: 'BE', orgType: 'large', headcount: '250_499' }), 'check');
assert.notEqual(verdictOf('131', { country: 'BE', orgType: 'sme', headcount: 'lt50' }), 'no');

// a saved profile's answers start the case: the same verdict as `callFit` on the document's facts for an unchanged university
const uni: Profile = { ...emptyProfile(), country: 'BE', legalForm: 'legal_person', applicantKind: 'company_or_research', orgKind: 'university', control: 'no' };
assert.equal(shownFit(callFit({ state: 'read', facts: raw('131').facts, programme: 'HORIZON', topic: raw('131').topicId }, uni, null)), 'no');
assert.equal(shownFit(answersFit(page('131'), answersOf(uni)!)), 'no');

// ---------------------------------------------------------------- 3. call 39: a US-controlled company and a China-only restriction

const control = (controller: Answers['controller']) => answersFit(page('39'), ask({ country: 'BE', orgType: 'large', controlledAbroad: 'yes', controller }))
  .result!.lines.find((l) => l.key === 'control')!;
assert.equal(control('other_non_eu').verdict, 'yes');
assert.equal(control('cn').verdict, 'no');
assert.equal(control('').verdict, 'check');
const size39 = answersFit(page('39'), ask({ country: 'BE', orgType: 'large' })).result!.lines.find((l) => l.key === 'sme')!;
assert.equal(size39.quote, undefined, 'the sentence "Any legal entity, regardless of its place of establishment" is not about size');

// ---------------------------------------------------------------- 2. the Cyber Defense Factory: its word names the condition, it ranks after topic matches

const ua: Profile = { ...emptyProfile(), country: 'UA', legalForm: 'legal_person', applicantKind: 'company_or_research', orgKind: 'company', headcount: 'lt50', inGroup: 'no', control: 'no' };
const cdf = callFit({ state: 'read', facts: raw('179').facts, programme: 'NATIONAL', topic: raw('179').topicId }, ua, null);
assert.equal(fitLabel(cdf).word, 'Only if your staff are French nationals');
assert.ok(fitLabel(cdf).word.startsWith(NATIONALITY_PREFIX));
const matching = callFit({ state: 'read', facts: raw('131').facts, programme: 'HORIZON', topic: raw('131').topicId }, ua, null);
assert.ok(fitOrder(matching, 1) < fitOrder(cdf, 0), 'a call with the visitor topic before the CDF');
assert.ok(fitOrder(cdf, 1) > fitOrder(matching, 1), 'among topic matches, the CDF after the others');
assert.ok(fitOrder(cdf, 0) > 0, 'and after the calls with no condition of that kind');

// ---------------------------------------------------------------- 5. the feed and the CSV name EDIP calls by their instrument, the programme once

assert.equal(programmeNameOf({ programme: 'EDIP-USI', programmeName: 'European Defence Fund' }), 'EDIP Ukraine Support Instrument');
assert.equal(programmeNameOf({ programme: 'EDIP', programmeName: 'European Defence Fund' }), 'European Defence Industry Programme');
assert.equal(programmeNameOf({ programme: 'HORIZON', programmeName: 'Horizon Europe' }), 'Horizon Europe');
const feedCall = {
  id: '118', slug: '118-missiles-ammunition-and-bombs', title: 'Missiles, ammunition and bombs', programme: 'EDIP-USI', programmeName: 'European Defence Fund',
  funder: 'European Commission', issuer: null, deadline: '2026-12-15T16:00:00Z', deadlineIsDate: false, budget: { amount: 150000000, currency: 'EUR' },
  budgetScope: 'topic', firstSeenAt: '2026-10-01T00:00:00Z', source: { sourceName: 'EU Funding and Tenders Portal (SEDIA)' },
} as unknown as Call;
const atom = buildFundingAtom([feedCall], { origin: 'https://example.test', query: '', describe: 'all', total: 1, generatedAt: '2026-10-24T00:00:00Z' });
const summary = /<summary type="text">([^<]*)<\/summary>/.exec(atom)![1];
assert.ok(summary.startsWith('European Commission, EDIP Ukraine Support Instrument. '), summary);
assert.ok(!summary.includes('European Defence Fund'), summary);
assert.ok(/ Budget [^.]*150[^.]* \(this topic\)\. /.test(summary), summary);

// ---------------------------------------------------------------- NCH vs NATCH (p05, 191)

assert.equal(otherTopicCode('DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH', 'Proposals under DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NCH must ...'), 'DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NCH');
assert.equal(otherTopicCode('DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH', 'DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH only'), null);
assert.equal(otherTopicCode('appel-projet', 'x'), null);

console.log('wp109 ok');
