/**
 * Self-check of the eligibility check's results pack (WP-156). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { PACK_CSV_HEADER, buildPack, callFactsOf, packCsvRows, type PackCall, type PackFit } from './eligibility-pack';
import { callFit } from './fit';
import { emptyProfile, type Profile } from './profile';
import { toCsv } from './csv';

const profile = (over: Partial<Profile>): Profile => ({ ...emptyProfile(), step: 6, ...over });
const ES = profile({ country: 'ES', sizeClass: 'small', inGroup: 'no', control: 'no' });
const LARGE = profile({ country: 'ES', sizeClass: 'large', control: 'no' });

const fact = (value: unknown, quote: string) => ({ value, note: null, quote, scope: 'call_document' });
const read = (facts: PackFit['facts']): PackFit => ({ state: 'read', programme: 'HORIZON', topic: 'HORIZON-x', facts });
const call = (id: string, fit: PackFit | null, over: Partial<PackCall> = {}): PackCall => ({
  id, slug: `${id}-call-${id}`, title: `Call ${id}`, programme: 'HORIZON', programmeName: 'Horizon Europe', topicId: `HORIZON-${id}`,
  deadline: '2026-11-20T17:00:00Z', deadlineIsDate: false, rolling: false, sourceUrl: `https://portal.example/${id}`, sourceName: 'EU portal', fit, ...over,
});

const open = read({ eligible_countries: fact('Legal entities established in EU Member States', 'Applicants must be established in an EU Member State.'),
  consortium_required: fact(false, 'A single applicant may apply.'), sme_only: fact(false, 'Open to all.'), ownership_control_restriction: fact(false, 'No restriction.') });
const smeOnly = read({ ...open.facts, sme_only: fact(true, 'Only SMEs may apply.') });
const calls = [call('1', open), call('2', smeOnly), call('3', { state: 'not_read', programme: 'HORIZON', topic: 'HORIZON-3', facts: {} }), call('4', null)];

// the verdict is the one of the list badges and the call page, on the same facts
assert.deepEqual(buildPack(calls, ES, null).rows.map((r) => r.result), [callFit(callFactsOf(open), ES, null), callFit(callFactsOf(smeOnly), ES, null)]);

// a small Spanish company fits both read calls; a large one is blocked by the SME-only call; unread calls are counted, never listed
const small = buildPack(calls, ES, null);
assert.deepEqual(small.rows.map((r) => r.call.id), ['1', '2']);
assert.deepEqual(small.counts, { yes: 2, check: 0, no: 0, unknown: 2 });
const large = buildPack(calls, LARGE, null);
assert.deepEqual(large.rows.map((r) => r.call.id), ['1']);
assert.equal(large.counts.no, 1);

// the lines carry the document's own sentence
const smeLine = small.rows[1].lines.find((l) => l.quote === 'Only SMEs may apply.');
assert.ok(smeLine, 'the SME rule is quoted');

// CSV: a row per line, the call's columns repeated, its page on the site and at the source
const rows = packCsvRows(small.rows, 'https://site.example');
assert.ok(rows.length >= small.rows.length);
assert.ok(rows.every((r) => r.length === PACK_CSV_HEADER.length));
const sme = rows.find((r) => r[8] === 'Only SMEs may apply.')!;
assert.deepEqual([sme[0], sme[1], sme[2], sme[3], sme[6], sme[9], sme[10]],
  ['Call 2', 'Horizon Europe', 'HORIZON-2', '2026-11-20T17:00:00Z', 'Allowed', 'https://site.example/funding/2-call-2', 'https://portal.example/2']);
// a date-only deadline is a date; a rolling call says so
assert.equal(packCsvRows([{ ...small.rows[0], call: call('5', open, { deadline: '2026-12-01T00:00:00Z', deadlineIsDate: true, rolling: true }) }], 'x')[0][3],
  '2026-12-01 (rolling, a cut-off)');
// a quote that a spreadsheet would read as a formula is defused by toCsv
const evil = packCsvRows([{ ...small.rows[0], lines: [{ key: 'k', label: 'Rule', verdict: 'check', reason: 'r', quote: '=HYPERLINK("x")' }] }], 'x');
assert.ok(toCsv(PACK_CSV_HEADER, evil).includes(`'=HYPERLINK`));
// a call whose verdict has no lines still has its row
assert.equal(packCsvRows([{ ...small.rows[0], lines: [] }], 'x').length, 1);

console.log('eligibility-pack checks ok');
