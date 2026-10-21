/**
 * Self-check of WP-64 (the Spain, Germany and NATO/EU readiness rules): the mirror of the seed in lib/mock carries the new rules with their
 * quotes and sources, the questions the wizard does not ask are shown without a step, the requirements only the roadmap can mark are sent
 * only once marked, and a national primary source is never called the Official Journal.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import mock from './mock/requirements.json';
import { emptyProfile, parseProfile, roadmapOnlyCodes, toRequest, visibleCodes, wizardAsks, withStatus, type Profile } from './profile';
import { originWords, programmeName, statusWords } from './readiness';
import type { RSource } from './readiness-types';

// the mirror: the Spanish MoD route and the general German and EU rules, each with a verbatim quote, a link and a date
const programmes = (mock as unknown as { programmes: { programmes: { code: string; name: string; rules: { rule: string; source: RSource; texts: Record<string, string> }[] }[] } }).programmes.programmes;
const es = programmes.find((p) => p.code === 'ES-MOD');
assert.ok(es, 'the Spanish defence supplier route is in the mirror');
assert.equal(es.name, 'Spanish defence supplier (MoD)');
assert.equal(es.rules.length, 21);
const general = programmes.find((p) => p.code === 'GENERAL');
assert.ok(general);
for (const code of ['DE-GHB-ADMISSION', 'DE-EXPORT-BAFA', 'EU-DUALUSE-EXPERT', 'EU-CERTIFIED-RECIPIENT']) assert.ok(general.rules.some((r) => r.rule === code), code);
for (const r of [...es.rules, ...general.rules.filter((x) => /^(DE|EU)-/.test(x.rule))]) {
  assert.ok(r.source.url.startsWith('http') && (r.source.text ?? '').startsWith('['), r.rule);
  assert.ok(/^2026-10-(17|20)$/.test(r.source.lastReviewed), r.rule);
}
const rid = es.rules.find((r) => r.rule === 'ES-RID');
assert.ok(rid && rid.source.text?.includes('REGISTRO DE LA INDUSTRIA DE DEFENSA (RID)'));
assert.ok(es.rules.find((r) => r.rule === 'ES-EXPORT-MIL')?.texts.consultant?.startsWith('Export classification'));
assert.equal(programmeName('ES-MOD'), 'Spanish defence supplier (MoD)');

// a ministry page or a national law is primary but not the Official Journal; EUR-Lex still is
const boe: RSource = { url: 'https://www.boe.es/eli/es/l/2011/08/01/24/con', ref: 'Ley 24/2011', text: null, origin: 'primary', verificationStatus: 'V', lastReviewed: '2026-10-20' };
assert.ok(!originWords(boe).includes('Official Journal') && originWords(boe).includes('2026-10-20'));
assert.ok(!statusWords('V', 'primary', boe.url).includes('Official Journal'));
assert.ok(statusWords('S', 'primary', boe.url).startsWith('Partly verified'));
assert.ok(originWords({ ...boe, url: 'https://eur-lex.europa.eu/eli/reg/2021/821/oj' }).includes('Official Journal'));
assert.ok(statusWords('V', 'primary', 'https://eur-lex.europa.eu/eli/reg/2021/821/oj').includes('Official Journal'));

// the wizard asks its own fields only; a WP-64 question or a requirement has no step to link to
assert.ok(wizardAsks('country') && wizardAsks('profile.export_intent'));
assert.ok(!wizardAsks('foreign_capital') && !wizardAsks('REQ-RID') && !wizardAsks('us_components'));

// the requirements only the roadmap can mark: not in the wizard, not sent until marked, kept once marked
assert.deepEqual(roadmapOnlyCodes('ES'), ['REQ-RID', 'REQ-PECAL', 'REQ-HSES-ES']);
assert.deepEqual(roadmapOnlyCodes('PL'), []);
assert.ok(!visibleCodes('ES').includes('REQ-RID'));
const p: Profile = { ...emptyProfile(), country: 'ES', step: 6 };
assert.equal(toRequest(p)?.statuses['REQ-RID'], undefined);
const marked = withStatus(p, 'REQ-RID', 'held');
assert.equal(toRequest(marked)?.statuses['REQ-RID'], 'held');
assert.equal(parseProfile(JSON.parse(JSON.stringify(marked))).statuses['REQ-RID'], 'held');
// a Spanish code is not sent for a company elsewhere
assert.equal(toRequest({ ...marked, country: 'PL' })?.statuses['REQ-RID'], undefined);

console.log('wp64 checks passed');
