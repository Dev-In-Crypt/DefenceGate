/**
 * Self-check of the "Can you apply?" verdict (WP-25, 17 October 2026). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { check, consortiumCondition, consortiumUnclear, covers, factDisplay, unclearConsortiumText, type EligibilityFacts, type Profile } from './eligibility-check';

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

// ---- WP-32, from the verifier's report (docs/verification/product/verify-eligibility-radar.md, 17 October 2026)
const q = (value: unknown, quote: string, note: string | null = null) => ({ value, note, quote, confidence: 1 });

// E1, call 78 (MCP INNOV-ADMIN): a call that names who may apply is not a plain "yes" for a company that is not plainly one of them.
const named: EligibilityFacts = { ...edf, entity_types: q(['Border or Coast Guard Authorities'], 'Applicants: border authorities') };
const companyOnly = { ...base, hasPartners: 'yes' as const };
assert.equal(check(edf, companyOnly).verdict, 'yes');
assert.equal(check(named, companyOnly).verdict, 'check', 'authorities only: not a yes for a company');
assert.equal(check(named, companyOnly).lines.find((l) => l.key === 'entity')!.verdict, 'check');
assert.equal(check(named, { ...base, orgType: '' }).lines.find((l) => l.key === 'entity')!.verdict, 'check', 'unknown kind');
assert.equal(check({ ...edf, entity_types: q(['Legal entities (public or private bodies)'], 'q') }, companyOnly).verdict, 'yes', 'a generic list still says yes');
assert.equal(check({ ...edf, entity_types: q(['Police Authorities', 'Public bodies', 'Private bodies'], 'q') }, companyOnly).verdict, 'yes');
assert.equal(check({ ...edf, entity_types: q(['universities', 'research organisations'], 'q') }, { ...companyOnly, orgType: 'university' }).verdict, 'yes');
assert.equal(check({ ...edf, entity_types: q(['universities', 'research organisations'], 'q') }, companyOnly).verdict, 'check');

// E2, call 96 (EDF DA) and 131 (EIC Defence): guarantees are a way round, so "controlled from abroad" is not "You cannot apply".
const guaranteed: EligibilityFacts = { ...edf, ownership_control_restriction: q(true, 'Entities controlled by a non-associated country may participate if they provide guarantees approved by the Member State.', 'Participation may be exceptionally permitted if approved guarantees are provided.') };
const abroad = { ...base, controlledAbroad: 'yes' as const };
assert.equal(check(guaranteed, abroad).verdict, 'check');
assert.match(check(guaranteed, abroad).lines.find((l) => l.key === 'control')!.reason, /approved guarantees are provided/, 'the exception is shown');
assert.equal(check({ ...edf, ownership_control_restriction: q(true, 'Not eligible: entities controlled by China.') }, abroad).verdict, 'check', 'call 60: only one country is excluded');
assert.equal(check({ ...edf, ownership_control_restriction: q(true, 'Entities must not be controlled from outside the eligible countries.') }, abroad).verdict, 'no', 'strict (call 144): still a no');
assert.equal(check({ ...edf, ownership_control_restriction: q(true, 'q', 'Stated in this topic’s own conditions. Guarantees are required.') }, abroad).verdict, 'check', 'call 131: the note names the route');

// F6, call 17 (Switzerland only) and 131: the sentence about the Member States is never shown to an EU applicant.
const swiss: EligibilityFacts = { eligible_countries: q('Switzerland (preselected candidates only)', 'q', 'The topic is limited to candidates preselected by Switzerland.') };
const de = check(swiss, { ...base, country: 'DE' });
assert.equal(de.verdict, 'check');
assert.ok(!/not an EU Member State/.test(de.lines[0].reason), de.lines[0].reason);
assert.match(check(swiss, { ...base, country: 'UA' }).lines[0].reason, /not an EU Member State/, 'but it is true for Ukraine');
assert.equal(check({ eligible_countries: q('Union, Ukraine, or an EEA member associated to Horizon Europe', 'q') }, { ...base, country: 'DE' }).verdict, 'yes', 'call 131 for a German applicant');
// F6, calls 118 and 144: "no consortium is required" next to a minimum number of entities, and with a condition in the note.
const contradiction = check({ ...edf, consortium_required: q(false, 'q'), min_entities: q(2, 'q') }, companyOnly);
assert.equal(contradiction.lines.find((l) => l.key === 'consortium')!.verdict, 'check');
assert.ok(!/^No consortium is required\.$/.test(contradiction.lines.find((l) => l.key === 'consortium')!.reason));
const noted = check({ ...edf, consortium_required: q(false, 'q', 'Consortia must include a Ukrainian entity.'), min_entities: q(1, 'q'), min_countries: q(1, 'q') }, companyOnly);
assert.match(noted.lines.find((l) => l.key === 'consortium')!.reason, /No consortium is required\. A condition applies: Consortia must include a Ukrainian entity/);
assert.equal(noted.verdict, 'check');
// U5, call 193 (EDIP): "No consortium is required" next to "at least 4 countries" is never printed as a bare "No".
const call193: EligibilityFacts = { ...edf, consortium_required: q(false, 'q', 'A single applicant is allowed only if it is a SEAP.'), min_entities: q(1, 'q'), min_countries: q(4, 'q') };
assert.equal(consortiumUnclear(call193), true, 'countries above one is enough');
assert.equal(consortiumUnclear({ ...call193, min_countries: q(1, 'q') }), false, 'one entity, one country: no conflict');
assert.equal(consortiumUnclear({ ...call193, consortium_required: q(true, 'q') }), false, 'a consortium that is required is not unclear');
assert.equal(consortiumUnclear({ ...call193, min_countries: undefined }), false, 'no number, no conflict');
assert.match(factDisplay('consortium_required', call193), /^The document is unclear, read it: it says no consortium is required and also asks for at least 4 countries.$/);
assert.notEqual(factDisplay('consortium_required', call193), 'No', 'never the bare word');
assert.equal(factDisplay('consortium_required', { ...call193, min_countries: q(1, 'q') }), 'No');
assert.equal(factDisplay('min_countries', call193), '4');
assert.match(unclearConsortiumText(call193), /at least 4 countries/);
assert.ok(!/legal entities/.test(unclearConsortiumText(call193)), 'a minimum of one entity is not mentioned');
const line193 = check(call193, companyOnly).lines.find((l) => l.key === 'consortium')!;
assert.equal(line193.verdict, 'check');
assert.match(line193.reason, /document is unclear/);
assert.match(line193.reason, /SEAP/, 'the note is carried');
// the same with a minimum number of entities only
assert.equal(consortiumUnclear({ ...edf, consortium_required: q(false, 'q'), min_entities: q(2, 'q'), min_countries: undefined }), true);

// ---- WP-40 (V2-C U2, V2-B10)
// U2, call 131: a list of SME kinds does not cover a large company ("Nothing in that list says a company like yours may").
const smeKinds: EligibilityFacts = { ...edf, entity_types: q(['SME company', 'Small mid-cap company (up to 499 employees)'], 'q') };
const largeCo = { ...base, orgType: 'large' as const };
assert.equal(check(smeKinds, largeCo).lines.find((l) => l.key === 'entity')!.verdict, 'check');
assert.match(check(smeKinds, largeCo).lines.find((l) => l.key === 'entity')!.reason, /Nothing in that list says a company like yours may/);
assert.equal(check(smeKinds, base).lines.find((l) => l.key === 'entity')!.verdict, 'yes', 'an SME is covered');
assert.equal(check({ ...edf, entity_types: q(['Large companies and SMEs'], 'q') }, largeCo).lines.find((l) => l.key === 'entity')!.verdict, 'yes', 'a list that names large companies covers them');
assert.equal(check({ ...edf, entity_types: q(['Legal entities (public or private bodies)'], 'q') }, largeCo).lines.find((l) => l.key === 'entity')!.verdict, 'yes');
assert.equal(covers('large', 'Small mid-cap company'), false);
assert.equal(covers('sme', 'Small mid-cap company'), true);
// call 118: "No consortium is required" is not the whole story when a single applicant must be Ukrainian.
const usiFacts: EligibilityFacts = { ...edf, consortium_required: q(false, 'Single applicants or consortia may apply.'), min_entities: q(1, 'q'), min_countries: undefined,
  single_applicant_allowed: q(true, 'q', 'A single applicant must be a legal entity established and having its executive management structure in Ukraine.') };
const usiLine = check(usiFacts, companyOnly).lines.find((l) => l.key === 'consortium')!;
assert.equal(usiLine.verdict, 'check');
assert.ok(!/^No consortium is required\.$/.test(usiLine.reason));
assert.match(usiLine.reason, /No consortium is required, but a single applicant may apply under a condition: A single applicant must be.*Ukraine/);
assert.equal(consortiumCondition(edf), null);
// a note that only says where the fact was read (the annexes, the topic's own text) is not a condition
const annexNote = 'General rule of the work programme annexes; the topic or the type of action may add or change it.';
assert.equal(consortiumCondition({ ...edf, consortium_required: { ...q(true, 'q', annexNote), scope: 'general' as const } }), null);
assert.equal(consortiumCondition({ ...edf, consortium_required: q(true, 'q', "Stated in this topic's own conditions.") }), null);
assert.match(consortiumCondition({ ...edf, consortium_required: q(true, 'q', `${annexNote} Only a SEAP may apply alone.`) })!, /condition to the consortium: Only a SEAP may apply alone\./);
assert.equal(consortiumCondition({ ...edf, single_applicant_allowed: q(true, 'q', "Stated in this topic's own conditions.") }), null);
console.log('eligibility-check checks passed');
