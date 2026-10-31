/**
 * Self-check of WP-162 (the "Who to sell to" report): the answer guard, the labels in one place (every flag and status has words, the
 * wording of section 3 is "who wins", never "who needs sub-suppliers"), the value line. Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { L, isSellReport, valueLine } from './sell-report';

// the shape of the API's answer for a report with every section empty (e2e/fixtures/sell-report-empty.json, trimmed)
const empty = {
  generatedAt: '2026-10-31T11:15:00Z', sample: false, brand: null,
  profile: { mode: 'B', name: null, slug: null, href: null, country: 'PL', cpv: ['03111000'], cpvTitles: {}, cpvFrom: 'request', nace: null, size: 'sme',
    held: [], classified: null, exports: null, usComponents: null, awards: null, projects: [] },
  market: { available: true, total: { procurements: 0, directive: 0, buyers: 0, awarded: 0, winners: 0 }, buyers: [] },
  open: { tenders: { rows: [], total: 0, href: null }, calls: { rows: [], words: [], matched: 0 } }, ending: null,
  qualify: { available: true, items: [], verdicts: [], notSourced: [] },
  steps: [{ key: 'codes', window: 'Days 1-30', text: 'Your CPV codes found no defence procurement.' }],
  sources: { coverage: '', winnersFrom: null, notes: [], projects: null, rules: '', disclaimer: L.disclaimer },
};
assert.ok(isSellReport(empty), 'the API answer of an empty report is a report');
assert.ok(!isSellReport(null) && !isSellReport({}) && !isSellReport({ ...empty, steps: null }));

for (const k of ['clearance', 'clearance_held', 'not_read'] as const) assert.ok(L.tenderFlag[k]);
for (const k of ['companies', 'public_only', 'sme_only', 'sme_only_large', 'not_stated'] as const) assert.ok(L.callFlag[k]);
for (const k of ['have', 'missing', 'consultant'] as const) assert.ok(L.statusWord[k]);
for (const k of ['prime', 'both', 'contract', 'not_stated', 'exporter', 'us_origin'] as const) assert.ok(L.applies[k]);

const words = JSON.stringify(Object.values(L).filter((v) => typeof v === 'string')) + L.mosaic(5) + L.winnersLead;
assert.ok(!/needs? sub-suppliers/i.test(words), 'section 3 says who wins, never who needs sub-suppliers');
assert.equal(L.s3, '3 · Who wins these contracts');
assert.ok(L.disclaimer.includes('not legal advice') && L.disclaimer.includes('not an eligibility decision'));

assert.equal(valueLine([]), null, 'no value is shown as missing, never as zero');
assert.equal(valueLine([{ currency: 'EUR', amount: 1200000.4, count: 3, lotEstimates: 0 }]), 'EUR 1,200,000 over 3 contracts');

console.log('wp162 ok');
