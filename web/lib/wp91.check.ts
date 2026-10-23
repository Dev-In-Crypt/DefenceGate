/**
 * Self-check of WP-91 (UX audit of 22 October 2026, section 6: the funding path, persona Piotr, a Polish drone-software start-up).
 *   1. an empty Open list says what opens next and what closed (never only "No calls match")
 *   2. "Can I apply?" for one country from the engine's outcomes; never a bare "No" for the consortium when a partner country is asked
 *   3. EDIP USI is labelled and filtered as its own programme
 *   4. the search's new synonyms (the same table as the API's), SME flags, EUDIS said not collected
 *   5. who may apply, as the API reads it
 *   7. the software branch of the readiness check; "Fits my profile" by the visitor's topics
 *   8. the calendar entries of one call
 *   9. an unverified issuer is said plainly, with NSPA's NCAGE page
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { callEntries } from './calendar-calls';
import { factDisplay, type EligibilityFacts } from './eligibility-check';
import { applySummary, countryGroup, emptyLine, topicScore, topicWords, whatItFunds } from './funding-path';
import { ignoredFilters, parseCallFilters, toQuery } from './filters';
import { allCalls, mockWho, queryCalls } from './mock/calls';
import requirements from './mock/requirements.json';
import { emptyProfile, skippedFields, toRequest, unanswered, type Profile } from './profile';
import { NSPA_NCAGE_URL, issuerFor } from './readiness';
import type { RIssuer } from './readiness-types';
import { SYNONYMS, notCollected, parseQuery } from './text-search';
import { PROGRAMMES } from './taxonomy';
import type { Call, RulesApply } from './types';

const REF = new Date('2026-10-12T08:00:00Z');

// ---------------------------------------------------------------- 4. the synonyms are the API's, row for row
const py = readFileSync(join(process.cwd(), '..', 'backend', 'dgate', 'textsearch.py'), 'utf8');
const block = py.slice(py.indexOf('SYNONYMS: tuple'), py.indexOf('MAX_TERMS ='));
const rows = [...block.matchAll(/\(([^()]*)\)/g)].map((m) => [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1])).filter((r) => r.length > 1);
assert.deepEqual(SYNONYMS, rows, 'web/lib/text-search.ts SYNONYMS equals backend/dgate/textsearch.py SYNONYMS');
const hit = (q: string, text: string) => parseQuery(q)?.matches(text) ?? false;
assert.ok(hit('software', 'Ground segment software') && hit('autonomy', 'Autonomous navigation') && hit('SME', 'Innowacje dla MŚP'));
assert.ok(hit('AI', 'machine learning for maintenance') && !hit('AI', 'against all odds'));
assert.deepEqual(notCollected('EUDIS challenge'), [notCollected('eudis')[0]]);
assert.match(notCollected('EUDIS')[0], /not a programme we collect/);
assert.ok(!/https?:/.test(notCollected('EUDIS')[0]), 'no link: no source in the repository names one');
assert.deepEqual(notCollected('drone'), []);
// the demo search reads the topic keywords and the SME flag as the API does
assert.ok(queryCalls({ q: 'software', status: 'all' }, REF).items.some((c) => c.scope.includes('Ground segment software')));
assert.ok(queryCalls({ q: 'SME', status: 'all' }, REF).items.some((c) => c.topicId === 'DIGITAL-ECCC-2026-CYBER-06-SME'));

// ---------------------------------------------------------------- 3. EDIP USI, its label and its filter
assert.equal(PROGRAMMES['EDIP-USI'].label, 'EDIP USI');
const usi = allCalls(REF, true).find((c) => c.programme === 'EDIP-USI')!;
assert.ok(usi && usi.topicId.startsWith('EDF-EDIP-USI-') && usi.openToUkraine === true);
assert.deepEqual(queryCalls({ programme: ['EDIP-USI'], status: 'all' }, REF).items.map((c) => c.id), [usi.id]);
assert.ok(queryCalls({ programme: ['EDF'], status: 'all' }, REF).items.some((c) => c.id === usi.id), 'EDF and EDIP holds it');
assert.deepEqual(parseCallFilters({ programme: 'edip-usi' }).programme, ['EDIP-USI']);
assert.deepEqual(ignoredFilters({ programme: 'EDIP-USI' }, 'funding'), []);
const reg = readFileSync(join(process.cwd(), 'lib', 'mock', 'regulation.json'), 'utf8');
assert.match(reg, /labelled EDIP USI on the funding pages and marked open to Ukraine/, '/regulation says the same as /funding');

// ---------------------------------------------------------------- 5. who may apply
assert.equal(mockWho('EDIP', 'EDF-EDIP-P-2027-FNLC-CPA-AMDS'), 'public');
assert.equal(mockWho('EDIP', 'EDF-EDIP-P-2026-2027-FNLC-SA-SEAP'), 'public');
assert.equal(mockWho('EDIP', 'EDF-EDIP-P-2026-FNLC-CSA-PREP'), 'public');
assert.equal(mockWho('EDIP-USI', 'EDF-EDIP-USI-2026-LS-IRA-MAB'), 'companies');
assert.equal(mockWho('HORIZON', 'HORIZON-CL3-2026-01-DRS-01'), null, 'nothing we hold says: no badge');
assert.equal(mockWho('DIGITAL', 'DIGITAL-ECCC-2026-CYBER-06-SME', true), 'companies');
assert.equal(toQuery({ who: 'companies' }), '?who=companies');
assert.equal(parseCallFilters({ who: 'everybody' }).who, undefined);
assert.match(ignoredFilters({ who: 'everybody' }, 'funding')[0], /who=everybody/);
for (const w of ['companies', 'public'] as const) {
  assert.ok(queryCalls({ who: w, status: 'all' }, REF).items.every((c) => c.whoMayApply === w));
}

// ---------------------------------------------------------------- 1. an empty Open list
const soon = { title: 'Drone swarms', openingDate: '2026-11-03T00:00:00Z', deadline: null } as unknown as Call;
const past = { title: 'Old call', deadline: '2026-09-30T15:00:00Z' } as unknown as Call;
assert.equal(emptyLine({ country: ['PL'], status: 'open' }, [soon], [past]), 'No open calls in Poland now; next expected: “Drone swarms”, opens 3 Nov 2026.');
assert.equal(emptyLine({ country: ['PL'], status: 'open' }, [], [past]), 'No open calls in Poland now, and none is announced; the latest that closed is “Old call”, on 30 Sep 2026.');
assert.match(emptyLine({ q: 'x', status: 'open' }, [], []), /^No open calls for this search now, none is announced and none has closed\.$/);

// ---------------------------------------------------------------- 2. "Can I apply?"
const o = (rule: string, title: string, outcome: 'met' | 'not_met' | 'conditional' | 'unknown', asks: string[] = [], reason = 'r') => ({ rule, title, outcome, asks, reason });
const usiRules = usi.rulesApply as RulesApply;
assert.equal(countryGroup('PL'), 'EU');
assert.equal(countryGroup('NO'), 'EEA_EFTA');
assert.equal(countryGroup('UA'), 'UA');
assert.equal(countryGroup('US'), 'OTHER');
const fromPl = applySummary({ rulesApply: usiRules, documentEligibility: null }, 'PL')!;
assert.equal(fromPl.verdict, 'check', 'never a plain yes without the Ukrainian partner');
assert.match(fromPl.lines.find((l) => l.key === 'country')!.text, /^From Poland: only together with a partner established in Ukraine/);
assert.ok(!fromPl.lines.some((l) => l.key === 'territory'), 'the territory note is for a Ukrainian company only');
const fromUa = applySummary({ rulesApply: usiRules, documentEligibility: null }, 'UA')!;
assert.match(fromUa.lines.find((l) => l.key === 'country')!.text, /^From Ukraine: your country is eligible/);
assert.ok(fromUa.lines.some((l) => l.key === 'territory' && /government does not control/.test(l.text)));
assert.equal(applySummary({ rulesApply: usiRules, documentEligibility: null }, 'US')!.verdict, 'no');
assert.equal(applySummary({ rulesApply: usiRules, documentEligibility: null }, ''), null);
const cpa: RulesApply = { ...usiRules, byCountry: { EU: [o('EDIP-ESTABLISH', 'Established in the Union', 'met')], EEA_EFTA: [], UA: [], OTHER: [] },
  forCompany: [o('EDIP-CPA-APPLICANT', 'Who may apply: contracting authorities, international organisations, SEAPs and the EDA', 'not_met')] };
const company = applySummary({ rulesApply: cpa, documentEligibility: null }, 'PL')!;
assert.equal(company.verdict, 'no');
assert.match(company.lines[0].text, /^Companies cannot apply to this call\. Who may apply: contracting authorities/);
assert.equal(applySummary({ rulesApply: cpa, documentEligibility: null }, 'PL', 'contracting_authority')!.lines[0].verdict, 'check');
const edfUa: RulesApply = { ...usiRules, forCompany: [], byCountry: { EU: [], EEA_EFTA: [], OTHER: [], UA: [o('EDF-ESTABLISH', 'Established in the Union or an associated country', 'conditional', [], 'Your company is established in Ukraine.')] } };
assert.match(applySummary({ rulesApply: edfUa, documentEligibility: null }, 'UA')!.lines[0].text, /^From Ukraine: only on a condition\. Your company is established in Ukraine\./);
const none = applySummary({ rulesApply: null, documentEligibility: null }, 'PL')!;
assert.equal(none.verdict, 'unknown', 'WP-93 (finding 6): nothing held is "Rules not read", never "Possible"');
assert.match(none.lines[0].text, /No rules of this programme are encoded here/);
// the call document's consortium fact of a Ukraine Support Instrument call: never a bare "No"
const q = (value: unknown, quote: string, note: string | null = null) => ({ value, quote, note, confidence: 1, scope: 'call_document' as const });
const usiFacts: EligibilityFacts = {
  eligible_countries: q('EU Member States; Ukraine', 'q', 'Legal entities established in the non-government controlled areas of Ukraine are not eligible for funding.'),
  consortium_required: q(false, 'Single applicants or consortia may apply.'),
  single_applicant_allowed: q(true, 'q', 'The single applicant must be established and have its executive management structure in Ukraine.'),
};
assert.notEqual(factDisplay('consortium_required', usiFacts), 'No');
assert.match(factDisplay('consortium_required', usiFacts), /^Not for every applicant\. A single applicant may apply under a condition: The single applicant must be established/);
const withFacts = applySummary({ rulesApply: usiRules, documentEligibility: { documentUrl: null, extractedAt: '2026-10-18T00:00:00Z', facts: usiFacts as NonNullable<Call['documentEligibility']>['facts'] } }, 'PL')!;
assert.match(withFacts.lines.find((l) => l.key === 'consortium')!.text, /^No consortium for every applicant: a single applicant may apply under a condition/);
assert.equal(whatItFunds({ title: 'Counter-drone', scope: ['Unmanned systems', 'Sensors'], actionType: null }), 'Counter-drone. The source’s keywords for this topic: Unmanned systems, Sensors.');
assert.equal(whatItFunds({ title: 'X', scope: [], actionType: null }), 'X. The source gives no topic keywords for it.');

// ---------------------------------------------------------------- 7. software or services; topics
const sw: Profile = { ...emptyProfile(), country: 'PL', legalForm: 'legal_person', offering: 'software_services', step: 6, componentPct: '50', restricted: 'yes', uaEeaComponents: 'yes' };
assert.deepEqual(skippedFields(sw), ['non_eu_component_cost_pct', 'restricted_third_country_component', 'components_from_ua_or_eea_efta']);
assert.deepEqual(skippedFields({ ...sw, offering: 'products' }), []);
const swReq = toRequest(sw)!.profile;
assert.deepEqual([swReq.non_eu_component_cost_pct, swReq.restricted_third_country_component, swReq.components_from_ua_or_eea_efta], [null, null, null],
  'not asked, so unknown to the rules (a check), never a "not applicable" the rule text does not support');
assert.ok(!unanswered(sw).some((u) => /component/.test(u.question)), 'the skipped questions are not listed as missing');
assert.ok(unanswered({ ...sw, offering: 'products', restricted: '', uaEeaComponents: '' }).some((u) => /component/.test(u.question)));
assert.deepEqual(topicWords('Software, autonomy;  counter-drone, x'), ['software', 'autonomy', 'counter drone']);
assert.equal(topicScore(['software', 'autonomy'], 'Algorithms for autonomous navigation'), 2);
assert.equal(topicScore(['software'], 'Naval platforms'), 0);

// ---------------------------------------------------------------- 8. the calendar entries of one call
const forthcoming = allCalls(REF).find((c) => c.status === 'forthcoming' && c.deadline && c.openingDate)!;
assert.deepEqual(callEntries(forthcoming, REF).map((e) => e.event), ['opens', 'deadline']);
const open = allCalls(REF).find((c) => c.status === 'open' && c.deadline && !c.rolling)!;
assert.deepEqual(callEntries(open, REF).map((e) => [e.event, e.key]), [['deadline', `funding-${open.id}`]]);
const closed = allCalls(REF).find((c) => c.status === 'closed')!;
assert.deepEqual(callEntries(closed, REF), []);

// ---------------------------------------------------------------- 9. who issues the NCAGE code in Poland
const ncage = (requirements as unknown as { requirements: Record<string, { issuers: RIssuer[] }> }).requirements['REQ-NCAGE'].issuers;
assert.equal(ncage.find((i) => i.country === '*')!.url, NSPA_NCAGE_URL, 'the NSPA page is the seed’s own row');
const seed = readFileSync(join(process.cwd(), '..', 'backend', 'seeds', 'requirements.json'), 'utf8');
assert.ok(seed.includes(NSPA_NCAGE_URL));
const pl = issuerFor('REQ-NCAGE', ncage, 'PL');
assert.equal(pl.kind, 'unverified');
if (pl.kind === 'unverified') {
  assert.match(pl.text, /^Not verified in our sources: we have not confirmed which body issues NCAGE codes in Poland\./);
  assert.equal(pl.link?.url, NSPA_NCAGE_URL);
}
assert.equal(issuerFor('REQ-NCAGE', ncage, 'ES').kind, 'verified');
const other = issuerFor('REQ-NCAGE', ncage, 'MX');
assert.ok(other.kind === 'verified' && other.issuer.country === '*', 'a country with no row of its own: the row for every other country (NSPA)');
assert.equal(issuerFor('REQ-RID', [], 'PL').kind, 'none');

console.log('wp91 ok');
