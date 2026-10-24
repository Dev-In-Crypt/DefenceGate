/**
 * Self-check of WP-102: the second eligibility regression set, the 60 new (profile, call) pairs two verifiers read against the official
 * documents on 24 October 2026 (data/wp102-pairs.json, built by backend/tests/wp102_golden.py). For every checkable pair the one verdict
 * (lib/fit.ts `callFit`) must be what the document says ("cannot" a "no"; "can only if" a "check" that names the condition; "can" a "yes" or a
 * "check"; a call whose rules we do not hold "Rules not read"), and for every fixture call and profile the browser's verdict is the API's
 * (backend/dgate/verdict.py wrote `expected`), line by line. Not part of the app. Run from web/:  node scripts/run-checks.mjs
 *
 * WP102_WRITE=1 writes `requests` (each profile's assessment request, lib/profile.ts toRequest) for the golden file.
 */
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import type { EligibilityFacts } from './eligibility-check';
import { ASSOCIATED, ASSOCIATION_SOURCES, check, countryStatus, factDisplay } from './eligibility-check';
import { NO_UA_PARTNER, PARTNER_ONLY_WORD, applicantFit, callFit, checkProfileOf, fitLabel, fitOrder, linesSummary, shownFit, topicsLine, verdictLines, type CallFacts, type FitResult } from './fit';
import { applySummary } from './funding-path';
import { parseProfile, toRequest, type Profile } from './profile';

const PATH = 'lib/data/wp102-pairs.json';
const data = JSON.parse(readFileSync(PATH, 'utf8'));
type RawCall = { programme: string; topic: string; state: CallFacts['state']; facts: Record<string, { value: unknown; note: string | null; quote: string; scope: string }> };
type Pair = { n: number; profile: string; call: string; document: string; mention: string | null };

const profileOf = (key: string): Profile => parseProfile(data.profiles[key].stored);

if (process.env.WP102_WRITE) {
  data.requests = Object.fromEntries(Object.keys(data.profiles).map((k) => [k, toRequest(profileOf(k))]));
  writeFileSync(PATH, `${JSON.stringify(data, null, 1)}\n`);
  console.log('wp102 requests written');
  process.exit(0);
}

// 1. The requests the golden file was built from are the ones the browser sends for these profiles.
for (const key of Object.keys(data.profiles)) assert.deepEqual(toRequest(profileOf(key)), data.requests[key], `${key}: the request`);

// 2. Every fixture call x profile: the list's facts and the call page's give one verdict, and it is the API's.
const asList = (c: RawCall): CallFacts => ({ state: c.state, programme: c.programme, topic: c.topic,
  facts: Object.fromEntries(Object.entries(c.facts).map(([k, f]) => [k, { value: f.value, note: f.note, quote: f.quote ?? '', confidence: 1, scope: f.scope as never }])) as EligibilityFacts });
const asPage = (c: RawCall): CallFacts => ({ ...asList(c), facts: Object.fromEntries(Object.entries(c.facts).map(([k, f]) => [k, { ...f, confidence: 0.9 }])) as unknown as EligibilityFacts });
const shape = (r: FitResult) => ({ fit: r.fit, shown: shownFit(r), word: fitLabel(r).word, conditions: r.conditions,
  lines: (r.result?.lines ?? []).map((l) => ({ key: l.key, verdict: l.verdict, reason: l.reason })) });
let compared = 0;
for (const key of Object.keys(data.profiles)) {
  for (const [id, call] of Object.entries(data.after as Record<string, RawCall>)) {
    const list = shape(callFit(asList(call), profileOf(key), data.assessments[key]));
    assert.deepEqual(shape(callFit(asPage(call), profileOf(key), data.assessments[key])), list, `${key} x call ${id}: list and call page`);
    assert.deepEqual(list, data.expected[`${key}|${id}`], `${key} x call ${id}: the browser and the API`);
    compared += 1;
  }
}

// 3. The pairs: every checkable one CORRECT, the uncheckable ones never a "yes" or a "no".
const words = (r: FitResult) => [...(r.result?.lines ?? []).map((l) => `${l.label} ${l.reason}`), ...r.conditions, fitLabel(r).word].join(' ');
const wrong: string[] = [];
let checkable = 0;
for (const p of data.pairs as Pair[]) {
  const r = callFit(asList(data.after[p.call]), profileOf(p.profile), data.assessments[p.profile]);
  const shown = shownFit(r);
  const named = !p.mention || words(r).includes(p.mention);
  if (process.env.WP102_PRINT) console.log(`${p.n} ${p.profile} ${p.call} ${p.document}: ${fitLabel(r).word}`);
  if (p.document === 'uncheckable') { assert.ok(shown === 'check' || shown === 'unknown', `pair ${p.n}: an uncheckable pair is neither a yes nor a no`); continue; }
  checkable += 1;
  const ok = p.document === 'not_held' ? shown === 'unknown'
    : p.document === 'cannot' ? shown === 'no' && named
    : p.document === 'can_if' ? shown === 'check' && named
    : shown === 'yes' || shown === 'check';
  if (!ok) wrong.push(`pair ${p.n} (${p.profile}, call ${p.call}): document ${p.document}${p.mention ? ` naming "${p.mention}"` : ''}, verdict ${fitLabel(r).word}`);
}
assert.deepEqual(wrong, [], `the verified pairs:\n${wrong.join('\n')}`);
assert.equal(checkable, 58);

// 4. Every rule read for these calls carries the sentence it rests on; the association list carries its source's clauses.
for (const [id, read] of Object.entries(data.readings as Record<string, Record<string, { quote: string; from: string }>>)) {
  for (const [k, f] of Object.entries(read)) assert.ok(f.quote.length > 20 && f.from, `call ${id} ${k}: a quote and where it is from`);
}
assert.ok(ASSOCIATED.HORIZON.yes.includes('CH') && ASSOCIATED.HORIZON.no.includes('LI'));
assert.ok(ASSOCIATION_SOURCES.HORIZON.listed.includes('Switzerland (associated to the entire Programme') && ASSOCIATION_SOURCES.HORIZON.no.startsWith('Liechtenstein'));
// 5. The pieces, as backend/tests/unit/test_wp102.py checks them in the API's engine.
const f = (value: unknown, note: string | null = null, scope = 'topic') => ({ value, note, quote: 'q', confidence: 1, scope }) as never;
const company: Profile = { ...parseProfile({}), country: 'PL', legalForm: 'legal_person', applicantKind: 'company_or_research', orgKind: 'company', headcount: 'lt50', inGroup: 'no', control: 'no' };
const form = { country: 'BE', orgType: 'sme' as const, hasPartners: '' as const, controlledAbroad: 'no' as const };
const kinds = { entity_types: f(['SME company', 'Small mid-cap company (up to 499 employees)']), sme_only: f(false) } as EligibilityFacts;
const sizeOf = (r: ReturnType<typeof check>) => r.lines.find((l) => l.key === 'sme')!;
assert.ok(sizeOf(check(kinds, form)).verdict === 'yes' && !/not reserved/.test(sizeOf(check(kinds, form)).reason));
assert.equal(sizeOf(check(kinds, { ...form, orgType: 'university' })).verdict, 'no');
const smeOnly = { sme_only: f(true, 'A small mid-cap (up to 499 employees) may apply only for investment component only support.', 'programme'), eligible_countries: f('EU Member States and countries associated to Horizon Europe', null, 'programme') } as EligibilityFacts;
const acc = { state: 'read' as const, programme: 'HORIZON', topic: 'HORIZON-EIC-2026-ACCELERATOR-01', facts: smeOnly };
assert.equal(fitLabel(callFit(acc, { ...company, orgKind: 'research', headcount: '250_499' }, null)).word, 'Blocked by: Organisation size');
const horizon = { programme: 'HORIZON', topic: 'HORIZON-CL3-2027-02-CS-ECCC-01' };
assert.equal(countryStatus(f('Member States and Associated Countries'), 'CH', horizon).verdict, 'yes');
assert.equal(countryStatus(f('Member States and Associated Countries'), 'LI', horizon).verdict, 'no');
const eccc = { eligible_countries: f('Member States and Associated Countries'), ownership_control_restriction: f(true, 'controlled by a non-eligible country or by a non-eligible country entity, shall not participate') } as EligibilityFacts;
const eea = checkProfileOf({ ...company, country: 'NO', control: 'ua_eea_only', controlCountry: 'eea' })!;
assert.equal(check(eccc, eea, horizon).lines.find((l) => l.key === 'control')!.verdict, 'check');
const us = checkProfileOf({ ...company, country: 'DE', control: 'other', controlCountry: 'other_non_eu' })!;
assert.equal(check({ ownership_control_restriction: { ...(f(true, "Stated in this topic's own conditions.") as object), quote: 'In order to guarantee the protection of the strategic interests of the Union, entities controlled by a non-eligible country' } } as unknown as EligibilityFacts, us).verdict, 'no');
const big = checkProfileOf({ ...company, headcount: '2000plus' })!;
const capped = check({ entity_types: f(['SMEs', 'non-SME industries']), non_sme_budget_cap: f(15), eligible_countries: f('EU Member States') } as EligibilityFacts, big);
assert.ok(capped.lines.find((l) => l.key === 'entity')!.verdict === 'yes' && /15 % of the proposed budget/.test(capped.lines.find((l) => l.key === 'cap')!.reason));
assert.deepEqual(check({ single_beneficiary_excludes: f('mid-caps and larger companies', null, 'programme'), eligible_countries: f('Member States') } as EligibilityFacts, big).lines.filter((l) => l.verdict === 'check').map((l) => l.key), ['single']);
assert.ok(/conflict of interest/.test(check({ procurement_conflict: f(true, null, 'general'), eligible_countries: f('EU Member States') } as EligibilityFacts, checkProfileOf(company)!).lines.find((l) => l.key === 'procurement')!.reason));
const rapid = callFit({ state: 'read', programme: 'NATIONAL', topic: '', facts: { max_group_headcount: f(1999, 'n', 'call_document') } as EligibilityFacts }, { ...company, country: 'ES' }, null);
assert.ok(shownFit(rapid) === 'check' && /was not read/.test(rapid.result!.lines.at(-1)!.reason));
const ncc = callFit({ state: 'read', programme: 'DIGITAL', topic: 'DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC', facts: { designated_applicants: f('National Coordination Centres', 'Others may take part in a consortium with them: x'), eligible_countries: f('EU Member States; EEA countries (Norway)') } as EligibilityFacts }, company, null);
assert.equal(fitLabel(ncc).word, PARTNER_ONLY_WORD);
assert.equal(applicantFit('EDF', 'EDF-EDIP-P-2027-FNLC-CPA-GNPS', { ...company, applicantKind: '' })!.fit, 'no');
assert.equal(applicantFit('EDF', 'EDF-EDIP-P-2027-FNLC-CPA-GNPS', { ...company, applicantKind: '', orgKind: '' })!.fit, 'check');

// 6. The call page and the list (one verdict, the short block, the order of "Fits my profile").
const cpa = callFit({ state: 'read', programme: 'EDF', topic: 'EDF-EDIP-P-2027-FNLC-CPA-SEAP', facts: { eligible_countries: f('EU Member States') } as EligibilityFacts }, company, null);
assert.equal(shownFit(cpa), 'no');
assert.ok(verdictLines(cpa).some((l) => l.verdict === 'no'), 'a box that lists the lines of a "no" never says "none is a no"');
assert.ok(!/none is a no/.test(linesSummary(verdictLines(cpa))));
const usiNoPartner = { fit: 'check' as const, result: { verdict: 'check' as const, lines: [] }, conditions: [NO_UA_PARTNER], blockedBy: [] };
assert.equal(verdictLines(usiNoPartner)[0].reason, NO_UA_PARTNER);
assert.ok(fitOrder(usiNoPartner, 0) > 0, 'a call that needs a partner the profile lacks goes after the rest');
const eligible = callFit({ state: 'read', programme: 'DIGITAL', topic: 'X', facts: { eligible_countries: f('EU Member States') } as EligibilityFacts }, company, null);
assert.ok(fitOrder(eligible, 1) < fitOrder(callFit({ state: 'read', programme: 'DIGITAL', topic: 'X', facts: { eligible_countries: f('EU Member States'), consortium_required: f(true) } as EligibilityFacts }, company, null), 1));
assert.ok(fitOrder(eligible, 2) < fitOrder(eligible, 1) && fitOrder(eligible, 0) === 0);
assert.equal(topicsLine(1, 1), 'Matches your topic');
assert.equal(topicsLine(1, 3), 'Matches 1 of your 3 topics');
const c131 = { rulesApply: null, documentEligibility: { facts: { entity_types: f(['SME company', 'Small mid-cap company (up to 499 employees)']), sme_only: f(false), investor_precommitment: f(true, null, 'programme'), eligible_countries: f('Union, Ukraine, or an EEA member associated to Horizon Europe') } } } as never;
const short = applySummary(c131, 'BE')!;
assert.ok(short.lines.some((l) => l.key === 'investor' && /20 %/.test(l.text)) && short.verdict === 'check', 'the 20 % investor rule is in the short block');
assert.ok(short.lines.some((l) => l.key === 'size' && /SMEs and small mid-caps/.test(l.text)));
assert.equal(factDisplay('sme_only', (c131 as { documentEligibility: { facts: EligibilityFacts } }).documentEligibility.facts), 'Not for SMEs alone, and not for every company: only SMEs and small mid-caps (up to 499 staff).');

console.log(`wp102 checks passed: ${checkable} checkable pairs correct (before WP-102: ${data.before.correct}/${data.before.checkable}), ${compared} call x profile verdicts equal to the API's`);
