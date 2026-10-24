// WP-108 self-check (run by scripts/run-checks.mjs): award values and version history, persona round 4 (24 October 2026).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { correctionLines, redatedLine, setAsideNote } from './award-lines';
import { cancelledSince, headlines } from './digest';
import { VALUE_KIND_NOT_STATED, csvValueKind } from './export-tables';
import { AWARD_NOTICE_VALUE_LABEL, noticeValueLabel, searchStatusLine, searchTenderNoun } from './tender-status';
import type { Digest, DigestTender } from './types';

// 1. a figure set aside against the notice's own lots (FASER 394720-2025) or its procedure (INCM 499753-2026)
const faser = setAsideNote({ amount: 7247040, kind: 'contract', currency: 'PLN', setAside: 7247040000, setAsideReason: 'lots' });
assert.ok(faser?.includes('exactly a thousand times the sum of its own lot values') && faser.includes('7,247,040,000'), faser ?? '');
const incm = setAsideNote({ amount: 1450000, kind: 'estimate', currency: 'EUR', setAside: 1159000000, setAsideReason: 'procedure' });
assert.ok(incm?.includes('over a hundred times the value the procedure’s own notice states') && incm.endsWith('the procedure’s estimate'), incm ?? '');
assert.ok(setAsideNote({ amount: 690000, kind: 'estimate', currency: 'EUR', setAside: 690000000, setAsideReason: 'procedure' })?.includes('exactly a thousand'));
assert.ok(setAsideNote({ kind: 'estimate', currency: 'EUR', setAside: 7274615930 })?.includes('over a hundred times the buyer’s estimate'), 'WP-103 unchanged');

// 3. the corrections said in the open: date, fields, before and after
const lines = correctionLines([{ detectedAt: '2026-10-15T06:49:22Z', changes: [
  { field: 'value_amount', label: 'Estimated value', before: 'EUR 45,980', after: 'EUR 38,000' },
  { field: 'published_at', label: 'Published', before: '28 Sep 2026', after: '3 Sep 2026' }] },
{ detectedAt: '2026-10-16T06:00:00Z', changes: [] }]);
assert.deepEqual(lines, ['Corrected 15 Oct 2026: Estimated value EUR 45,980 to EUR 38,000; Published 28 Sep 2026 to 3 Sep 2026']);
// 4. the source's re-dating with the award: said apart, never a line of the buyer's change
assert.equal(redatedLine({ redated: [{ field: 'published_at', label: 'Published', before: '28 Sep 2026', after: '3 Sep 2026' }] }),
  'The source dated the notice again when it published the award (Published 28 Sep 2026 to 3 Sep 2026): not a change by the buyer, and not counted as one.');
assert.equal(redatedLine({ redated: [] }), null);
assert.equal(redatedLine({}), null, 'an older API: nothing');
assert.match(readFileSync('components/dg/version-timeline.tsx', 'utf8'), /redatedLine\(ver\) && <span[^>]*data-redated>/);
const page = readFileSync('app/(public)/tenders/[slug]/page.tsx', 'utf8');
assert.ok(page.indexOf('data-correction-lines') > page.indexOf('data-corrections') && page.indexOf('data-correction-lines') < page.indexOf('<Details summary={`${corrections.length}'),
  'the lines stand open above the fold');

// 5. the digest: a new notice cancelled since says so (AU ZLT-50)
const row = (statusNative: string | null, kind: 'new' | 'amended' = 'new') => ({ id: '1', slug: '1-x', kind, day: '2026-10-12', title: 'ZLT-50', buyerName: 'AU',
  country: 'PL', deadline: null, estimatedValue: null, changes: [], statusNative }) as DigestTender;
assert.equal(cancelledSince(row('cancelled')), true);
assert.equal(cancelledSince(row('cancelled', 'amended')), false);
assert.equal(cancelledSince(row(null)), false, 'an older stored issue: nothing claimed');
assert.deepEqual(headlines({ callsNew: [], callsOpened: [], callsAmended: [], callsClosing: [], tendersNew: [row('cancelled')], tendersAmended: [] } as unknown as Digest),
  ['New notice (cancelled since): ZLT-50']);
assert.match(readFileSync('components/digest/digest-view.tsx', 'utf8'), /cancelledSince\(t\) && <span data-cancelled><Tag>Cancelled since<\/Tag>/);

// 6. an award's labels: its status in the search, its own value not called an estimate (V7000 375694-2026)
const ref = new Date('2026-10-24T12:00:00Z');
const award = { status: 'closed' as const, deadline: null, statusNative: 'awarded' };
assert.equal(searchStatusLine(award, ref), 'Awarded');
assert.equal(searchStatusLine({ status: 'open', deadline: '2026-11-20T10:00:00Z', statusNative: 'open' }, ref), 'Deadline 20 Nov 2026');
assert.equal(searchStatusLine({ status: 'open', deadline: null, statusNative: 'open' }, ref), 'No deadline stated');
assert.equal(searchTenderNoun([award], 1, ref), 'tender', 'not "1 open tender" for an award');
assert.equal(searchTenderNoun([{ status: 'open', deadline: '2026-11-20T10:00:00Z', statusNative: 'open' }], 1, ref), 'open tender');
assert.equal(searchTenderNoun([award, { status: 'open', deadline: '2026-11-20T10:00:00Z', statusNative: 'open' }], 5, ref), 'tenders');
assert.equal(noticeValueLabel({ statusNative: 'awarded', valueKind: 'total' }), AWARD_NOTICE_VALUE_LABEL);
assert.equal(noticeValueLabel({ statusNative: 'open', valueKind: 'total' }), 'Estimated value');
assert.equal(noticeValueLabel({ statusNative: 'awarded', valueKind: 'estimated' }), 'Estimated value');
assert.match(readFileSync('app/(public)/search/page.tsx', 'utf8'), /searchStatusLine\(t\)/);

// 7. the tender file: one word for a value kind not stated, and for no value
assert.equal(VALUE_KIND_NOT_STATED, 'not stated');
assert.equal(csvValueKind({ valueKind: 'total', statusNative: 'awarded', source: { sourceId: 'ted' } }), VALUE_KIND_NOT_STATED);
assert.match(readFileSync('lib/export.ts', 'utf8'), /: null\) \?\? VALUE_KIND_NOT_STATED,/, 'a row without a value says "not stated", not an empty cell');

console.log('wp108 checks passed');
