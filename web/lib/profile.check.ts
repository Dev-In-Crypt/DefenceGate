/**
 * Self-check of the browser-side profile of the readiness check (WP-29). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { emptyProfile, isFinished, parsePct, parseProfile, toRequest, visibleCodes, withStatus, type Profile } from './profile';

const ua: Profile = {
  ...emptyProfile(), step: 6, name: 'Secret Ltd', sizeClass: 'small', country: 'UA', legalForm: 'legal_person', control: 'no', uaOccupied: 'no', regime: 'dual_use',
  componentPct: '20', restricted: 'no', uaEeaComponents: 'no', safeRole: 'contractor', classified: 'no', exportIntent: 'outside_eu',
};

// Nothing can be asked before a country is chosen.
assert.equal(toRequest(emptyProfile()), null);

// The request holds the thirteen fields the rules read and the statuses; the name and the size never travel.
const req = toRequest(ua)!;
assert.deepEqual(req.profile, {
  country: 'UA', legal_form: 'legal_person', applicant_kind: null, executive_management_country: 'UA', third_country_control: 'no', ua_non_government_controlled_area: false,
  non_eu_component_cost_pct: 20, restricted_third_country_component: false, components_from_ua_or_eea_efta: false, safe_role: 'contractor', handles_classified: false,
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
const unsure: Profile = { ...ua, control: 'unsure', restricted: 'unsure', classified: '', componentPct: '', exportIntent: '', regime: '', uaEeaComponents: 'unsure', safeRole: 'unsure', legalForm: '' };
const u = toRequest(unsure)!.profile;
assert.deepEqual([u.third_country_control, u.restricted_third_country_component, u.handles_classified, u.non_eu_component_cost_pct, u.export_intent, u.product_regime, u.components_from_ua_or_eea_efta, u.safe_role, u.legal_form],
  [null, null, null, null, null, 'unknown', null, null, null]);

// The legal form and the SAFE role are sent as given (D2, D5); a stored value that is not one of ours becomes the empty answer.
assert.equal(toRequest({ ...ua, legalForm: 'natural_person' })!.profile.legal_form, 'natural_person');
assert.equal(toRequest({ ...ua, safeRole: 'other_supplier' })!.profile.safe_role, 'other_supplier');
assert.equal(parseProfile({ ...ua, legalForm: 'sole_trader', safeRole: 'boss' }).legalForm, '');
assert.equal(parseProfile({ ...ua, legalForm: 'sole_trader', safeRole: 'boss' }).safeRole, '');
assert.equal(parseProfile({ ...ua, uaEeaComponents: 'maybe' }).uaEeaComponents, '');

// V2-B1: what the organisation is. Unanswered is unknown (null), never "a company"; a stored value that is not one of ours is dropped.
assert.equal(emptyProfile().applicantKind, '');
assert.equal(toRequest({ ...ua, applicantKind: 'contracting_authority' })!.profile.applicant_kind, 'contracting_authority');
assert.equal(toRequest({ ...ua, applicantKind: 'company_or_research' })!.profile.applicant_kind, 'company_or_research');
assert.equal(parseProfile({ ...ua, applicantKind: 'ministry' }).applicantKind, '');
assert.equal(parseProfile({ ...ua, applicantKind: 'seap' }).applicantKind, 'seap');

// Executive management elsewhere is sent as that country; chosen but left empty it is unknown.
assert.equal(toRequest({ ...ua, managementSameCountry: false, managementCountry: 'CH' })!.profile.executive_management_country, 'CH');
assert.equal(toRequest({ ...ua, managementSameCountry: false })!.profile.executive_management_country, null);

// A share is a number from 0 to 100.
assert.equal(parsePct('35'), 35);
assert.equal(parsePct('12,5'), 12.5);
assert.equal(parsePct(' 0 '), 0);
assert.equal(parsePct(''), null);
assert.equal(parsePct('101'), null);
assert.equal(parsePct('abc'), null);
assert.equal(parsePct('-1'), null);

// Whatever is in storage is read field by field: junk becomes the empty answer.
assert.deepEqual(parseProfile(null), emptyProfile());
assert.deepEqual(parseProfile('x'), emptyProfile());
assert.deepEqual(parseProfile([]), emptyProfile());
assert.deepEqual(parseProfile({ version: 2, country: 'UA' }), emptyProfile());
const read = parseProfile({ ...ua, country: 'ukraine', control: 'maybe', componentPct: '1e9', step: 99, statuses: { 'REQ-PIC': 'held', 'REQ-NOPE': 'held', 'REQ-NCAGE': 'done' }, name: 'x'.repeat(500) });
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
console.log('profile.check ok');
