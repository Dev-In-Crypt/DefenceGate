/**
 * Self-check of WP-73 (fixes from the frontend QA of 21 October 2026):
 *   MJ-3  an item the visitor was not asked about is sent as "unknown", never "not held"; the HSEM is asked, not assumed;
 *   MJ-4  the TS mirror of the verdict (the supplier roadmap's red) reads a "conditional" obligation as binding, like the engine;
 *   MJ-1  the CPV search covers the whole official vocabulary (9,454 codes), whole words of the titles, curated words and code prefixes,
 *         and the full list is imported by lib/cpv-full.ts only (a chunk of its own, loaded on the supplier page and its report);
 *   MJ-2  no CPV code is required to save;
 *   MJ-5  every question a page of this check asks links there (askedAt).
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { cpvSearch } from './cpv';
import { CPV_FULL, CPV_FULL_SOURCE } from './cpv-full';
import {
  CERTIFICATES, REGISTRATIONS, askedAt, clearanceAnswer, cpvProblem, emptyProfile, emptySupplier, savedSupplier, supplierFields, supplierProblems,
  toRequest, withClearance, withHeld, type Profile,
} from './profile';
import { supplierRoadmap } from './supplier-roadmap';
import type { Assessment, ProgrammeAssessment, RuleResult } from './readiness-types';

// ------------------------------------------------------------- MJ-3: unasked is unknown
const es: Profile = { ...emptyProfile(), country: 'ES', classified: 'yes' };
const saved = savedSupplier(withHeld(es, CERTIFICATES.find((c) => c.key === 'ISO9001')!, true));
const sent = toRequest(saved)!.statuses;
for (const code of ['REQ-PIC', 'REQ-EXPORT', 'REQ-REOCE', 'REQ-FSC-ES']) assert.equal(sent[code], 'unknown', `${code}: the supplier page does not ask it`);
for (const h of [...CERTIFICATES, ...REGISTRATIONS]) if (h.code) assert.equal(sent[h.code], h.code === 'REQ-ISO9001' ? 'held' : 'not_held', `${h.code}: the page shows it`);
assert.ok(Object.entries(sent).every(([c, v]) => v !== 'not_held' || [...CERTIFICATES, ...REGISTRATIONS].some((h) => h.code === c)), 'only what the page showed is "not held"');
// a finished wizard (step 4 passed, with "We do not hold it" chosen) still sends "not held"
const wizard = toRequest({ ...es, step: 6 })!.statuses;
for (const code of ['REQ-PIC', 'REQ-EXPORT', 'REQ-REOCE', 'REQ-FSC-ES', 'REQ-NCAGE']) assert.equal(wizard[code], 'not_held', code);
assert.equal(toRequest({ ...es, step: 4 })!.statuses['REQ-PIC'], 'unknown', 'step 4 shown but not passed');
// the HSEM question: yes held, no not held, not sure leaves it unknown
const yes = withClearance(es, 'REQ-FSC-ES', 'yes');
assert.equal(toRequest(yes)!.statuses['REQ-FSC-ES'], 'held');
assert.equal(clearanceAnswer(yes, 'REQ-FSC-ES'), 'yes');
assert.equal(toRequest(withClearance(es, 'REQ-FSC-ES', 'no'))!.statuses['REQ-FSC-ES'], 'not_held');
const unsure = withClearance(yes, 'REQ-FSC-ES', 'unsure');
assert.equal(toRequest(unsure)!.statuses['REQ-FSC-ES'], 'unknown');
assert.equal(clearanceAnswer(unsure, 'REQ-FSC-ES'), 'unsure', 'the answer itself is kept');
assert.equal(clearanceAnswer({ ...es, statuses: { 'REQ-FSC-ES': 'held' } }, 'REQ-FSC-ES'), 'yes', 'the wizard\'s answer shows on the page');
assert.equal(clearanceAnswer({ ...withClearance(es, 'REQ-FSC-ES', 'no'), statuses: { 'REQ-FSC-ES': 'held' } }, 'REQ-FSC-ES'), 'yes', 'a later step 4 answer wins');
assert.equal(toRequest({ ...unsure, step: 6 })!.statuses['REQ-FSC-ES'], 'unknown', '"not sure" stays unknown after the wizard was finished');
// the EEA question goes to the general rule for any EU company, not to a company elsewhere
const de: Profile = { ...emptyProfile(), country: 'DE', supplier: { ...emptySupplier(), answers: { receives_eea_defence_products: 'yes' } } };
assert.equal(supplierFields(de).receives_eea_defence_products, true);
assert.equal(supplierFields({ ...de, country: 'US' }).receives_eea_defence_products, undefined);

// ------------------------------------------------------------- MJ-4: the mirror of the engine's rule in the supplier roadmap
const rule = (over: Partial<RuleResult>): RuleResult => ({
  rule: 'ES-NCAGE', title: 'NCAGE', outcome: 'to_obtain', reason: 'r', obligation: 'conditional', kind: 'registration', requirement: 'REQ-NCAGE',
  note: null, denominator: null, asks: [], consultant: null,
  source: { url: 'https://example.test', ref: 'ref', text: null, origin: 'primary', verificationStatus: 'V', lastReviewed: '2026-10-20' }, ...over,
} as RuleResult);
const card = (rules: RuleResult[]): ProgrammeAssessment => ({ programme: 'ES-MOD', name: 'Spanish defence supplier (MoD)', kind: 'route', summary: '', legalBasis: null,
  sourceUrl: '', verdict: 'obtain', incomplete: false, blocking: [], conditions: [], toObtain: ['ES-NCAGE'], missing: [], rules } as unknown as ProgrammeAssessment);
const answer = (rules: RuleResult[]) => ({ assessments: [card(rules)], general: [], roadmap: { steps: [] }, consultants: [] } as unknown as Assessment);
const red = (r: RuleResult) => supplierRoadmap(answer([r]), es).items.find((i) => i.key === 'REQ-NCAGE')?.rag;
assert.equal(red(rule({})), 'red', 'a conditional registration that applies is needed now');
assert.equal(red(rule({ obligation: 'recommended' })), 'amber', 'a recommendation is never "needed now"');

// ------------------------------------------------------------- MJ-1: the full vocabulary
assert.equal(CPV_FULL.size, 9454);
assert.ok(CPV_FULL_SOURCE.source.includes('publications.europa.eu/resource/dataset/cpv') && CPV_FULL_SOURCE.licence.includes('CC BY 4.0'));
assert.equal(CPV_FULL.get('44521000'), 'Miscellaneous padlocks and locks');
const find = (q: string) => cpvSearch(q, 50, CPV_FULL);
for (const w of ['casting', 'castings', 'steel', 'aluminium', 'forging', 'machining']) assert.ok(find(w).length > 0, `${w} finds a code`);
assert.ok(find('4452').length > 0 && find('4452').every((c) => c.code.startsWith('4452')), 'a code prefix');
assert.ok(find('steel').every((c) => /\bsteel/i.test(c.title)), 'whole words of the official titles');
assert.ok(!find('gun').some((c) => /Gunmetal/.test(c.title)), 'never a piece of a longer word');
assert.ok(find('drone').some((c) => c.code === '35613000'), 'the curated product words still count');
// only lib/cpv-full.ts imports the full list, and only dynamically from a component
const files = (dir: string): string[] => readdirSync(dir).flatMap((f) => { const p = join(dir, f); return statSync(p).isDirectory() ? files(p) : [p]; });
const src = [...files('app'), ...files('components'), ...files('lib')].filter((f) => /\.(ts|tsx)$/.test(f) && !f.endsWith('.check.ts'));
const statics = src.filter((f) => /from ['"][^'"]*(cpv-full\.json|cpv-full)['"]/.test(readFileSync(f, 'utf8')));
assert.deepEqual(statics.map((f) => f.replace(/\\/g, '/')), ['lib/cpv-full.ts'], 'the full list is imported statically by lib/cpv-full.ts only');
const dynamic = src.filter((f) => readFileSync(f, 'utf8').includes("import('@/lib/cpv-full')")).map((f) => f.replace(/\\/g, '/'));
assert.deepEqual(dynamic, ['components/readiness/use-readiness.ts']);

// ------------------------------------------------------------- MJ-2 and MJ-5
assert.equal(cpvProblem([]), null);
assert.deepEqual(supplierProblems({ ...es }).map((x) => x.id), [], 'a Spanish profile with no CPV code can be saved');
assert.equal(askedAt('legal_form'), '/readiness?step=1');
assert.equal(askedAt('profile.handles_classified'), '/readiness?step=5');
assert.equal(askedAt('pecal_certificate_wanted'), '/readiness/supplier#q-pecal_certificate_wanted');
assert.equal(askedAt('pecal_system_9_months'), '/readiness/supplier#sp-spain', 'a follow-up links to the questions where its parent is asked');
assert.equal(askedAt('REQ-RID'), '/readiness/supplier#q-REQ-RID');
assert.equal(askedAt('REQ-FSC-ES'), '/readiness/supplier#q-REQ-FSC-ES');
assert.equal(askedAt('REQ-HSES-ES'), '/readiness/supplier#q-REQ-HSES-ES');
assert.equal(askedAt('REQ-PIC'), '/readiness?step=4');
// WP-68: the German questions are asked on the supplier page now; a field no page asks still has no link
assert.equal(askedAt('de_vs_nfd'), '/readiness/supplier#sp-germany');
assert.equal(askedAt('pecal_unknown_field'), null);
// the RID rule no longer says the questionnaire does not ask
const seed = readFileSync('../backend/seeds/requirements.json', 'utf8');
assert.ok(!seed.includes('does not ask yet whether you hold a current RID'), 'the stale RID sentence is gone');

console.log('wp73 checks passed');
