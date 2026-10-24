/**
 * Self-check of the browser-side profile of the readiness check (WP-29). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { PROFILE_KEY, answerProblems, controlChoice, emptyProfile, exportProfile, firstStepToAnswer, importProfile, isFinished, managementCountryOf, parsePct, parseProfile, pctProblem, stepOfField, toRequest, unanswered, visibleCodes, withControlChoice, withStatus, type Profile } from './profile';

const ua: Profile = {
  ...emptyProfile(), step: 6, management: 'same', name: 'Secret Ltd', sizeClass: 'small', country: 'UA', legalForm: 'legal_person', control: 'no', uaOccupied: 'no', regime: 'dual_use',
  componentPct: '20', restricted: 'no', uaComponents: 'no', eeaComponents: 'no', safeRole: 'contractor', classified: 'no', exportIntent: 'outside_eu',
};

// Nothing can be asked before a country is chosen.
assert.equal(toRequest(emptyProfile()), null);

// The request holds the fourteen fields the rules read and the statuses; the name and the size never travel.
const req = toRequest(ua)!;
assert.deepEqual(req.profile, {
  country: 'UA', legal_form: 'legal_person', applicant_kind: null, executive_management_country: 'UA', third_country_control: 'no', ua_non_government_controlled_area: false,
  non_eu_component_cost_pct: 20, restricted_third_country_component: false, components_from_ua: false, components_from_eea_efta: false, ua_partner: null, safe_role: 'contractor', handles_classified: false,
  product_regime: 'dual_use', export_intent: 'outside_eu',
});
assert.ok(!JSON.stringify(req).includes('Secret'), 'the company name must not leave the browser');
assert.ok(!JSON.stringify(req).includes('small'), 'the size class must not leave the browser');
assert.equal(Object.keys(req.statuses).length, 7);
assert.ok(Object.values(req.statuses).every((s) => s === 'not_held'));

// Spain asks about two more requirements; Ukraine's question about occupied areas is not sent for others.
const es: Profile = { ...ua, country: 'ES', uaOccupied: 'yes', statuses: { 'REQ-ISO9001': 'held' } };
assert.deepEqual(visibleCodes('ES').slice(-2), ['REQ-REOCE', 'REQ-FSC-ES']);
assert.equal(visibleCodes('UA').length, 7);
const esReq = toRequest(es)!;
assert.equal(esReq.profile.ua_non_government_controlled_area, null);
assert.equal(esReq.statuses['REQ-ISO9001'], 'held');
assert.equal(Object.keys(esReq.statuses).length, 9);

// "Not sure" and an empty answer are unknown (null), never "no".
const unsure: Profile = { ...ua, control: 'unsure', restricted: 'unsure', classified: '', componentPct: '', exportIntent: '', regime: '', uaComponents: 'unsure', eeaComponents: 'unsure', safeRole: 'unsure', legalForm: '' };
const u = toRequest(unsure)!.profile;
assert.deepEqual([u.third_country_control, u.restricted_third_country_component, u.handles_classified, u.non_eu_component_cost_pct, u.export_intent, u.product_regime, u.components_from_ua, u.components_from_eea_efta, u.safe_role, u.legal_form],
  [null, null, null, null, null, 'unknown', null, null, null, null]);

// The legal form and the SAFE role are sent as given (D2, D5); a stored value that is not one of ours becomes the empty answer.
assert.equal(toRequest({ ...ua, legalForm: 'natural_person' })!.profile.legal_form, 'natural_person');
assert.equal(toRequest({ ...ua, safeRole: 'other_supplier' })!.profile.safe_role, 'other_supplier');
assert.equal(parseProfile({ ...ua, legalForm: 'sole_trader', safeRole: 'boss' }).legalForm, '');
assert.equal(parseProfile({ ...ua, legalForm: 'sole_trader', safeRole: 'boss' }).safeRole, '');
assert.equal(parseProfile({ ...ua, uaComponents: 'maybe' }).uaComponents, '');

// V2-B1: what the organisation is. Unanswered is unknown (null), never "a company"; a stored value that is not one of ours is dropped.
assert.equal(emptyProfile().applicantKind, '');
assert.equal(toRequest({ ...ua, applicantKind: 'contracting_authority' })!.profile.applicant_kind, 'contracting_authority');
assert.equal(toRequest({ ...ua, applicantKind: 'company_or_research' })!.profile.applicant_kind, 'company_or_research');
assert.equal(parseProfile({ ...ua, applicantKind: 'ministry' }).applicantKind, '');
assert.equal(parseProfile({ ...ua, applicantKind: 'seap' }).applicantKind, 'seap');

// Executive management elsewhere is sent as that country; chosen but left empty it is unknown.
assert.equal(toRequest({ ...ua, management: 'other', managementCountry: 'CH' })!.profile.executive_management_country, 'CH');
assert.equal(toRequest({ ...ua, management: 'other' })!.profile.executive_management_country, null);

// WP-53, T5: no radio is ticked for the visitor. An empty answer is unknown (null), asked for, and never "the same country".
assert.equal(emptyProfile().management, '');
assert.equal(toRequest({ ...ua, management: '' })!.profile.executive_management_country, null);
assert.equal(toRequest({ ...ua, management: 'same' })!.profile.executive_management_country, 'UA');
assert.equal(managementCountryOf({ ...ua, management: '' }), null);
assert.ok(unanswered({ ...ua, management: '' }).some((u) => u.step === 2 && /executive management/.test(u.question)), 'the unanswered question is listed');
assert.ok(!unanswered(ua).some((u) => /executive management/.test(u.question)));
assert.ok(unanswered({ ...ua, management: 'other', managementCountry: '' }).some((u) => u.question === 'Country of the executive management'));

// WP-53: the stored block of version 1 is read, and a stored "same country" is not trusted (it is what the pre-ticked radio left behind).
const legacy = { ...JSON.parse(JSON.stringify(ua)), version: 1, managementSameCountry: true };
delete legacy.management;
assert.equal(parseProfile(legacy).management, '', 'a version 1 "same country" cannot be told from the radio that was ticked for the visitor');
assert.equal(parseProfile({ ...legacy, managementSameCountry: false, managementCountry: 'CH' }).management, 'other');
assert.equal(parseProfile({ ...legacy, managementSameCountry: false, managementCountry: 'CH' }).managementCountry, 'CH');
assert.equal(parseProfile(legacy).version, 5, 'it is written back as the current version (5 since WP-99)');
assert.equal(parseProfile(legacy).country, 'UA', 'the other answers are kept');
assert.equal(parseProfile(legacy).uaPartner, '');
assert.equal(parseProfile({ ...ua, management: 'sideways' }).management, '');
assert.equal(PROFILE_KEY, 'dg.profile.v1', 'the key keeps its name; the version is inside the block');
const imported = importProfile(JSON.stringify(legacy));
assert.ok(imported.ok && imported.profile.management === '' && imported.profile.version === 5, 'a version 1 file can still be loaded');

// WP-53, T21: the partner questions. Unanswered and "not sure" are unknown (null), never "no"; a Ukrainian company is not asked.
const pl: Profile = { ...ua, country: 'PL', uaOccupied: '' };
assert.equal(emptyProfile().uaPartner, '');
assert.equal(toRequest(pl)!.profile.ua_partner, null);
assert.equal(toRequest({ ...pl, uaPartner: 'yes' })!.profile.ua_partner, true);
assert.equal(toRequest({ ...pl, uaPartner: 'no' })!.profile.ua_partner, false);
assert.equal(toRequest({ ...pl, uaPartner: 'unsure' })!.profile.ua_partner, null);
assert.equal(toRequest({ ...ua, uaPartner: 'yes' })!.profile.ua_partner, null, 'a Ukrainian company is the entity itself: a leftover answer is not sent');
assert.ok(!unanswered(pl).some((u) => /takes part/.test(u.question)), 'optional: the USI card asks for it itself, and the list of unanswered questions stays what it was');
assert.equal(stepOfField('ua_partner'), 2);
assert.equal(parseProfile({ ...ua, uaPartner: 'maybe', seapPartner: 'yes' }).uaPartner, '');
assert.equal(parseProfile({ ...ua, uaPartner: 'maybe', seapPartner: 'yes' }).seapPartner, 'yes');
assert.equal(JSON.stringify(toRequest({ ...pl, seapPartner: 'yes' })).includes('seap'), false, 'no rule of the programmes reads the SEAP answer: it stays in the browser');

// A share is a number from 0 to 100.
assert.equal(parsePct('35'), 35);
assert.equal(parsePct('12,5'), 12.5);
assert.equal(parsePct(' 0 '), 0);
assert.equal(parsePct(''), null);
assert.equal(parsePct('101'), null);
assert.equal(parsePct('abc'), null);
assert.equal(parsePct('-1'), null);
assert.equal(parsePct('100'), 100);
assert.equal(parsePct('99.99'), 99.99);
assert.equal(parsePct('.5'), 0.5);

// WP-53, T6: a value that is not a number from 0 to 100 has a reason, blocks the step, and is named wherever it is treated as missing.
for (const bad of ['150', '100.5', '1,5,5', '.', 'abc', '-5', '12345678', '1e2', '0x10', '1 000']) {
  assert.equal(pctProblem(bad), 'Enter a number from 0 to 100.', bad);
  assert.equal(toRequest({ ...ua, componentPct: bad })!.profile.non_eu_component_cost_pct, null, `${bad} is not sent`);
  const problems = answerProblems({ ...ua, componentPct: bad });
  assert.equal(problems.length, 1, bad);
  assert.equal(problems[0].step, 3);
  assert.match(problems[0].text, /not a number from 0 to 100, so it is treated as not given/);
  assert.ok(problems[0].text.includes(bad.trim()), 'the text quotes what was entered');
}
for (const fine of ['', '  ', '0', '100', '12,5', '99.99', '7.']) {
  assert.equal(pctProblem(fine), null, JSON.stringify(fine));
  assert.deepEqual(answerProblems({ ...ua, componentPct: fine }), [], JSON.stringify(fine));
}
assert.equal(parseProfile({ ...ua, componentPct: '150' }).componentPct, '150', 'kept as typed, so that its problem can be shown');
assert.equal(parseProfile({ ...ua, componentPct: 'x'.repeat(40) }).componentPct.length, 12);
assert.equal(answerProblems({ ...ua, management: 'other', managementCountry: '' })[0].step, 2, 'another country chosen but not named is also said');
assert.match(answerProblems({ ...ua, management: 'other', managementCountry: '' })[0].text, /did not choose which one, so that answer is treated as not given/);
assert.deepEqual(answerProblems(ua), []);

// Whatever is in storage is read field by field: junk becomes the empty answer.
assert.deepEqual(parseProfile(null), emptyProfile());
assert.deepEqual(parseProfile('x'), emptyProfile());
assert.deepEqual(parseProfile([]), emptyProfile());
assert.deepEqual(parseProfile({ version: 6, country: 'UA' }), emptyProfile(), 'a version this code does not know (6, after WP-99 made 5 the current one) is refused');
assert.deepEqual(parseProfile({ version: 0, country: 'UA' }), emptyProfile());
const read = parseProfile({ ...ua, country: 'ukraine', control: 'maybe', componentPct: '', step: 99, statuses: { 'REQ-PIC': 'held', 'REQ-NOPE': 'held', 'REQ-NCAGE': 'done' }, name: 'x'.repeat(500) });
assert.equal(read.country, '');
assert.equal(read.control, '');
assert.equal(read.componentPct, '');
assert.equal(read.step, 1);
assert.deepEqual(read.statuses, { 'REQ-PIC': 'held' });
assert.equal(read.name.length, 120);
assert.deepEqual(parseProfile(JSON.parse(JSON.stringify(ua))), ua);

// Marking a requirement done changes only that status.
const done = withStatus(ua, 'REQ-PIC', 'held');
assert.equal(done.statuses['REQ-PIC'], 'held');
assert.equal(toRequest(done)!.statuses['REQ-PIC'], 'held');
assert.equal(toRequest(done)!.statuses['REQ-NCAGE'], 'not_held');
assert.equal(ua.statuses['REQ-PIC'], undefined, 'the original is not changed');

assert.equal(isFinished(ua), true);
assert.equal(isFinished({ ...ua, step: 3 }), false);
assert.equal(isFinished(null), false);

// U7: what is still unanswered is named, in the order of the wizard, and "Change my answers" opens at the first of them.
// WP-93: the size and group questions are new; a complete profile answers them, a version 3 one is told they are missing (step 1)
const ua4: Profile = { ...ua, orgKind: 'company', headcount: 'lt50', inGroup: 'no' };
assert.deepEqual(unanswered(ua4), [], 'a complete profile has nothing missing');
assert.deepEqual(unanswered(ua).map((u) => u.step), [1, 1, 1], 'a profile without the WP-93 answers is asked them');
assert.equal(firstStepToAnswer(ua4), 1, 'nothing missing: the first step');
const partial: Profile = { ...ua4, step: 6, regime: '', restricted: '', classified: '' };
assert.deepEqual(unanswered(partial).map((u) => u.step), [3, 3, 5]);
assert.equal(firstStepToAnswer(partial), 3);
assert.match(unanswered(partial)[1].question, /third country/);
assert.equal(unanswered({ ...ua4, control: '' })[0].step, 2);
assert.deepEqual(unanswered(emptyProfile()).slice(0, 2).map((u) => u.step), [1, 1]);
assert.ok(unanswered({ ...ua, country: 'UA', uaOccupied: '' }).some((u) => /area of Ukraine/.test(u.question)));
assert.ok(!unanswered({ ...ua, country: 'PL', uaOccupied: '' }).some((u) => /area of Ukraine/.test(u.question)), 'only a Ukrainian company is asked');
assert.deepEqual(['country', 'legal_form', 'third_country_control', 'safe_role', 'export_intent', 'something_else'].map(stepOfField), [1, 1, 2, 3, 5, 1]);

// U7: the answers can be taken to another computer or kept for another client, and a block that is not ours is refused.
const written = exportProfile(partial);
const back = importProfile(written);
assert.ok(back.ok);
if (back.ok) assert.deepEqual({ ...back.profile, updatedAt: null }, { ...parseProfile(partial), updatedAt: null }, 'what was written is what is read back');
assert.equal(importProfile('{"version":5}').ok, false);
assert.equal(importProfile('{}').ok, false);
assert.equal(importProfile('[1,2]').ok, false);
assert.equal(importProfile('not json').ok, false);
assert.equal(importProfile('x'.repeat(30000)).ok, false, 'a size limit');
const hostile = importProfile(JSON.stringify({ ...ua, country: 'ZZZ', control: 'maybe', statuses: { 'REQ-PIC': 'held', EVIL: 'held' }, __proto__: { polluted: 1 } }));
assert.ok(hostile.ok && hostile.profile.country === '' && hostile.profile.control === '' && !('EVIL' in hostile.profile.statuses), 'every field is checked on the way in');

// WP-99: version 5 keeps Ukraine and the EEA EFTA states apart. A version 4 block is read so: "only by Ukraine or an EEA EFTA state" with
// its country is the answer of that country, without it unanswered again; a joint "no" (or "not sure") about components answers both
// questions, a joint "yes" neither (it does not say which).
const v4 = { ...ua, version: 4, uaEeaComponents: 'no', uaComponents: undefined, eeaComponents: undefined };
assert.equal(parseProfile(v4).version, 5);
assert.deepEqual([parseProfile(v4).uaComponents, parseProfile(v4).eeaComponents], ['no', 'no']);
assert.deepEqual([parseProfile({ ...v4, uaEeaComponents: 'yes' }).uaComponents, parseProfile({ ...v4, uaEeaComponents: 'yes' }).eeaComponents], ['', '']);
assert.deepEqual([parseProfile({ ...v4, uaEeaComponents: 'unsure' }).uaComponents, parseProfile({ ...v4, uaEeaComponents: 'unsure' }).eeaComponents], ['unsure', 'unsure']);
assert.equal(controlChoice(parseProfile({ ...v4, control: 'ua_eea_only', controlCountry: 'ua' })), 'ua');
assert.equal(controlChoice(parseProfile({ ...v4, control: 'ua_eea_only', controlCountry: 'eea' })), 'eea');
assert.equal(parseProfile({ ...v4, control: 'ua_eea_only', controlCountry: 'unsure' }).control, '', 'neither country: asked again');
assert.ok(unanswered(parseProfile({ ...v4, control: 'ua_eea_only', controlCountry: '' })).some((x) => /controlled from outside the EU/.test(x.question)));
// the choice and what is kept, and the request: a Ukrainian-controlled company sends the control and the country
const byUa = withControlChoice(ua, 'ua');
assert.deepEqual([byUa.control, byUa.controlCountry, controlChoice(byUa)], ['ua_eea_only', 'ua', 'ua']);
assert.deepEqual([toRequest(byUa)!.profile.third_country_control, toRequest(byUa)!.profile.control_country], ['ua_eea_only', 'ua']);
assert.deepEqual([withControlChoice(byUa, 'no').control, withControlChoice(byUa, 'no').controlCountry], ['no', '']);
const byCn = { ...withControlChoice(ua, 'other'), controlCountry: 'cn' as const };
assert.equal(withControlChoice(byCn, 'other').controlCountry, 'cn', 'the country after "another country" is kept');
assert.deepEqual([toRequest({ ...ua, uaComponents: 'yes', eeaComponents: 'no' })!.profile.components_from_ua, toRequest({ ...ua, uaComponents: 'yes', eeaComponents: 'no' })!.profile.components_from_eea_efta], [true, false]);
assert.ok(!('components_from_ua_or_eea_efta' in toRequest(ua)!.profile), 'the joint answer is not sent any more');
console.log('profile.check ok');
