/**
 * Self-check of WP-131 (round-7 legal-content audit, 25 October 2026): the sentence on what leaves the browser is made from the two request
 * builders and names every field they send (and nothing they do not), and every page that says how many questions a check asks reads the
 * range from lib/question-counts.ts. Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DE_QUESTIONS, DUAL_USE_QUESTION, ES_QUESTIONS, EU_QUESTION, emptyProfile, emptySupplier, toRequest, type Profile } from './profile';
import { demandRequest } from './demand';
import { DEMAND_SENTENCE, DEMAND_WORDS, NEVER_SENT, VERDICT_SENTENCE, VERDICT_WORDS, WHAT_IS_SENT } from './sent-copy';
import { STEPS_QUESTIONS, SUPPLIER_QUESTIONS, rangeWords } from './question-counts';
import { sourceKinds, sourceFreshness, statusReasonLine } from './source-status';
import { checkedLine } from './regulation';
import { feedSubtitle } from './atom';

// ---------------------------------------------------------------- 1. what is sent, from the request builders

/** A profile with every answer given, for one country and offering (every follow-up opened by a "yes"). */
function full(country: string, offering: Profile['offering'] = 'products'): Profile {
  const answers: Record<string, 'yes'> = {};
  for (const q of [...ES_QUESTIONS, ...DE_QUESTIONS, DUAL_USE_QUESTION]) answers[q.field] = 'yes';
  answers[EU_QUESTION] = 'yes';
  return {
    ...emptyProfile(), country, step: 6, name: 'Acme Components S.L.', sizeClass: 'small', offering, topics: 'drone software',
    legalForm: 'legal_person', applicantKind: 'company_or_research', orgKind: 'company', headcount: '50_249', inGroup: 'yes', groupHeadcount: '250_499',
    management: 'other', managementCountry: 'FR', control: 'other', controlCountry: 'cn', investor: 'yes', uaOccupied: 'yes', uaPartner: 'yes',
    seapPartner: 'yes', regime: 'dual_use', componentPct: '12', restricted: 'yes', uaComponents: 'yes', eeaComponents: 'yes', safeRole: 'contractor',
    statuses: { 'REQ-ISO9001': 'held' }, classified: 'yes', exportIntent: 'outside_eu',
    supplier: { ...emptySupplier(), region: 'ES-MD', foreignOwner: 'yes', foreignCountry: 'US', nace: '25.50', cpv: ['34300000', '34320000'],
      processes: ['machining'], usComponents: 'yes', answers, euFunding: 'yes' },
  };
}

// a military product opens the Spanish defence-material question; a dual-use one the EU dual-use question
const profiles = [full('ES'), { ...full('ES'), regime: 'military' as const }, full('DE'), full('PL'), full('UA'), full('US'), full('ES', 'software_services')];
const sent = new Set<string>();
for (const p of profiles) {
  const r = toRequest(p);
  assert.ok(r, `${p.country}: a request`);
  for (const k of Object.keys(r.profile)) sent.add(k);
  sent.add('statuses');
}
const named = new Map(VERDICT_WORDS.flatMap((g) => g.fields.map((f) => [f, g.words] as const)));
for (const f of sent) assert.ok(named.has(f), `${f} is sent and the sentence does not say so (lib/sent-copy.ts VERDICT_WORDS)`);
for (const f of named.keys()) assert.ok(sent.has(f), `${f} is in the sentence but no request carries it`);
for (const g of VERDICT_WORDS) assert.ok(VERDICT_SENTENCE.includes(g.words), `the sentence says “${g.words}”`);
// the staff counts are sent (round 7: "the company name and size ... are never sent"), the name, size class and topics are not
assert.ok(sent.has('headcount') && sent.has('group_headcount'));
const body = JSON.stringify(profiles.map((p) => toRequest(p)));
for (const v of ['Acme Components', 'drone software', 'ES-MD', '25.50', 'machining', '"small"']) assert.ok(!body.includes(v), `${v} never leaves the browser`);
assert.ok(!/\bsize_class\b|"name"/.test(body));

// the demand map: its fields, each named; the codes, the seven countries and the own country (round 7: "those codes alone")
const demand = demandRequest(full('ES'));
assert.ok(demand);
assert.deepEqual(Object.keys(demand).sort(), Object.keys(DEMAND_WORDS).sort(), 'every field of the demand request is named');
for (const w of Object.values(DEMAND_WORDS)) assert.ok(DEMAND_SENTENCE.includes(w));
assert.match(DEMAND_WORDS.countries, /^the seven countries/);
assert.ok(!JSON.stringify(demand).includes('Acme'));
assert.ok(WHAT_IS_SENT.includes(VERDICT_SENTENCE) && WHAT_IS_SENT.includes(DEMAND_SENTENCE) && WHAT_IS_SENT.includes(NEVER_SENT));
assert.doesNotMatch(WHAT_IS_SENT, /alone|nothing else/, 'no "codes alone" or "nothing else of the profile"');

// the pages say it with these words, not their own
for (const page of ['app/(public)/readiness/page.tsx', 'app/(public)/readiness/supplier/page.tsx', 'app/(public)/readiness/spain-automotive/page.tsx']) {
  const src = readFileSync(page, 'utf8');
  assert.match(src, /\{WHAT_IS_SENT\}/, `${page} says what is sent from lib/sent-copy.ts`);
  assert.doesNotMatch(src, /never sent|codes alone|nothing else/, `${page}: no hand-written list`);
}
for (const page of ['lib/pricing.ts', 'app/(public)/pack/page.tsx', 'components/funding/fit-badge.tsx']) {
  assert.doesNotMatch(readFileSync(page, 'utf8'), /answers stay in your browser/, `${page}: the answers are sent to compute a result`);
}

// ---------------------------------------------------------------- 2. question counts, read from one place

assert.equal(rangeWords(SUPPLIER_QUESTIONS), '17 to 53');
assert.equal(rangeWords(STEPS_QUESTIONS), '24 to 35');
for (const page of ['app/(public)/page.tsx', 'app/(public)/check/page.tsx', 'app/(public)/readiness/page.tsx', 'components/funding/call-readiness.tsx']) {
  const src = readFileSync(page, 'utf8');
  assert.match(src, /rangeWords\((STEPS|SUPPLIER)_QUESTIONS\)/, `${page} reads the range from lib/question-counts.ts`);
  assert.doesNotMatch(src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, ''), /\b\d+ to \d+ (questions|in all)/, `${page}: no range written by hand`);
}

// ---------------------------------------------------------------- 3. the home page's trust line, one status per source card

assert.equal(sourceKinds([...Array(8)].map(() => ({ type: 'tenders' })).concat([...Array(8)].map(() => ({ type: 'grants' })))), '8 tender and 8 funding sources');
assert.equal(sourceKinds([{ type: 'tenders' }, { type: 'grants' }]), '1 tender and 1 funding source');
assert.equal(sourceKinds([{ type: 'grants' }, { type: 'grants' }]), '2 funding sources');

// e-Zamówienia on 25 Oct: refused (HTTP 403), partial, 0 records, run that day, the API says stale (a daily source that fetched nothing all day)
const REF = new Date('2026-10-25T15:40:00Z');
const ezam = { id: 'pl_ezam', status: 'partial' as const, lastRunAt: '2026-10-25T14:34:00Z', coverage: 0, records: 0, updateFreq: 'daily', staleAfterHours: 72, stale: true,
  statusReason: 'The source refuses access (HTTP 403); no new records arrive from it until it lets us in again. Refused since 24 Oct 2026 06:45 UTC.' };
const f = sourceFreshness(ezam, REF);
assert.deepEqual(f, { kind: 'stale', note: 'Stale: no run of the last day fetched anything' }, 'one status, and no "last ran 0 days ago"');
assert.match(statusReasonLine(ezam, f.kind) ?? '', /^Why it is stale: The source refuses access \(HTTP 403\)/);
// a run late by its age keeps the age; a failed run stays failed and its note no longer says "Stale"
assert.deepEqual(sourceFreshness({ ...ezam, lastRunAt: '2026-10-20T14:34:00Z' }, REF), { kind: 'stale', note: 'Stale: last ran 5 days ago' });
assert.deepEqual(sourceFreshness({ ...ezam, status: 'failed', lastRunAt: '2026-10-20T14:34:00Z' }, REF), { kind: 'failed', note: 'Last ran 5 days ago' });
assert.equal(sourceFreshness({ ...ezam, staleAfterHours: 24, lastRunAt: '2026-10-24T14:34:00Z' }, REF).note, 'Stale: last ran 1 day ago');
assert.equal(sourceFreshness({ ...ezam, lastRunAt: '2026-10-24T14:34:00Z' }, REF).note, 'Stale: no run of the last day fetched anything', 'not late by age: the API’s daily rule');

// ---------------------------------------------------------------- 4. the feed's subtitle counts the funding entries on top

assert.match(feedSubtitle(14, 2127, 400, { page: 1, pages: 6, size: 400 }, 3),
  /holds the newest 400 of the 2,127 changes; the page lists them all\. The older ones are on the next pages of this feed \(400 a page\)\. It also carries 3 funding-call entries\.$/);
assert.match(feedSubtitle(14, 30, 30, { page: 1, pages: 1, size: 400 }, 1), /It also carries 1 funding-call entry\.$/);
assert.ok(!feedSubtitle(14, 30, 30, { page: 1, pages: 1, size: 400 }).includes('funding-call'));

// ---------------------------------------------------------------- 5. the tracker's check date

const say = (d: string) => d;
assert.equal(checkedLine([{ checkedOn: '2026-10-18' }, { checkedOn: '2026-10-18' }], say), 'Every entry’s source was last checked on 2026-10-18, none since.');
assert.equal(checkedLine([{ checkedOn: '2026-10-25' }, { checkedOn: '2026-10-18' }], say),
  'The entries’ sources were last checked between 2026-10-18 and 2026-10-25; each entry gives its own date.');
assert.equal(checkedLine([], say), null);

console.log('wp131 checks passed');
