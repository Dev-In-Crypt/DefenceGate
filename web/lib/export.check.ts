/**
 * Self-check of the export helpers (CSV cells, calendar-file text). Not part of the app and not imported by it.
 * Run from web/:  npx tsc lib/export.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/export.check.js
 */
import assert from 'node:assert/strict';
import { csvCell, isMidnight, isoUtc, toCsv } from './csv';
import { foldLine, icsText } from './ics';
import { cpvPrefix } from './cpv';
import { ExportRunner, Gate, TtlCache, collectByCursor, listOrder, tooBroad } from './export-cache';

// Spreadsheet formulas are defused, ordinary text is not touched.
for (const bad of ['=SUM(A1)', '+1', '-1+2', '@cmd', '\tx', '\rx']) assert.ok(csvCell(bad).replace(/^"/, '').startsWith("'"), bad);
assert.equal(csvCell('Dostawa'), 'Dostawa');
assert.equal(csvCell(-5), '-5');
assert.equal(csvCell('a,b'), '"a,b"');
assert.equal(csvCell('say "hi"'), '"say ""hi"""');
assert.equal(csvCell('line\nbreak'), 'line break');
assert.equal(csvCell(null), '');
assert.equal(toCsv(['a', 'b'], [['1', '=2']]), '﻿a,b\r\n1,\'=2\r\n');
// WP-116: the file's first three bytes are the UTF-8 byte-order mark, and "ó" is two bytes after it (not Latin-1)
assert.deepEqual([...Buffer.from(toCsv(['Dirección'], []), 'utf8').subarray(0, 6)], [0xef, 0xbb, 0xbf, 0x44, 0x69, 0x72]);
assert.equal(Buffer.from(toCsv(['ó'], []), 'utf8').subarray(3, 5).toString('hex'), 'c3b3');

// Dates.
assert.equal(isoUtc('2026-11-26T16:00:00Z'), '2026-11-26T16:00:00Z');
assert.equal(isoUtc('2026-11-26T00:00:00Z', true), '2026-11-26');
assert.equal(isoUtc('not a date'), '');
assert.equal(isMidnight('2026-11-26T00:00:00Z'), true);
assert.equal(isMidnight('2026-11-26T00:01:00Z'), false);

// Calendar-file text: escaped, capped, folded at 75 octets without splitting a character.
assert.equal(icsText('a;b,c\\d\ne', 50), 'a\\;b\\,c\\\\d e');
assert.ok(Array.from(icsText('x'.repeat(300), 120)).length <= 120);
const folded = foldLine(`SUMMARY:${'ł'.repeat(80)}`);
for (const line of folded.split('\r\n')) assert.ok(new TextEncoder().encode(line).length <= 75, 'fold');
assert.equal(folded.replace(/\r\n /g, ''), `SUMMARY:${'ł'.repeat(80)}`);

// CPV: the significant digits are what the tenders filter takes.
assert.equal(cpvPrefix('35000000'), '35');
assert.equal(cpvPrefix('35300000'), '353');
assert.equal(cpvPrefix('35121700'), '351217');

// The widest export, every status and every scope with nothing narrowing it, is refused before the database.
assert.equal(tooBroad({ status: 'all', scope: 'all' }), true);
assert.equal(tooBroad({ status: 'all', scope: 'all', country: ['DE'] }), false);
assert.equal(tooBroad({ status: 'all', scope: 'all', q: 'radar' }), false);
assert.equal(tooBroad({ status: 'all', scope: 'core' }), false);
assert.equal(tooBroad({ status: 'open', scope: 'all' }), false);

// One client cannot hold the whole gate: its third uncached build is refused, another client's is not.
void (async () => {
  const runner = new ExportRunner<string>(new TtlCache(1000, 10), new Gate(6), 2);
  const release: Array<() => void> = [];
  const slow = (v: string) => () => new Promise<string>((resolve) => release.push(() => resolve(v)));
  const a1 = runner.get('a1', slow('1'), 'client-a');
  const a2 = runner.get('a2', slow('2'), 'client-a');
  assert.deepEqual(await runner.get('a3', slow('3'), 'client-a'), { busy: true });
  const b1 = runner.get('b1', slow('4'), 'client-b');
  release.splice(0).forEach((r) => r());
  assert.deepEqual(await a1, { value: '1' });
  assert.deepEqual(await a2, { value: '2' });
  assert.deepEqual(await b1, { value: '4' });
  // The slots come back once the builds finish.
  const again = runner.get('a3', slow('3'), 'client-a');
  release.splice(0).forEach((r) => r());
  assert.deepEqual(await again, { value: '3' });
  console.log('export checks passed');
})();

// A cursor export degrades instead of failing: a "too slow" page is asked again once, smaller, after a pause.
void (async () => {
  const slow = new Error('503');
  const calls: Array<[string | null, number]> = [];
  const rows = Array.from({ length: 2500 }, (_, i) => ({ id: String(i), deadline: null as string | null }));
  const make = (failFirstAt: number | null) => async (cursor: string | null, size: number) => {
    calls.push([cursor, size]);
    if (failFirstAt !== null && calls.length === failFirstAt) throw slow;
    const at = cursor ? Number(cursor) : 0;
    const items = rows.slice(at, at + size);
    return { items, nextCursor: at + size < rows.length ? String(at + size) : null };
  };
  const pauses: number[] = [];
  const opts = { retryable: (e: unknown) => e === slow, sleep: async (ms: number) => { pauses.push(ms); } };
  const ok = await collectByCursor(make(2), 2000, opts);
  assert.equal(ok.items.length, 2000);
  assert.equal(ok.more, true, 'cut at the cap with rows left');
  assert.deepEqual(pauses, [1000], 'one pause');
  assert.deepEqual(calls.map(([, s]) => s), [1000, 1000, 500, 500], 'the failed page is repeated at half the size and the rest keeps it');
  calls.length = 0;
  const all = await collectByCursor(make(null), 3000, opts);
  assert.equal(all.items.length, 2500);
  assert.equal(all.more, false);
  // Two failures in a row on one page are an error, not a loop.
  await assert.rejects(collectByCursor(async () => { throw slow; }, 100, opts), slow);
  // An error that is not "too slow" is not retried.
  let n = 0;
  await assert.rejects(collectByCursor(async () => { n += 1; throw new Error('bad'); }, 100, opts));
  assert.equal(n, 1);
  // The list's order for a file read by id.
  const d = (id: string, deadline: string | null) => ({ id, deadline });
  assert.deepEqual(listOrder([d('a', null), d('b', '2026-12-01T00:00:00Z'), d('c', '2026-11-01T00:00:00Z')], 'open').map((x) => x.id), ['c', 'b', 'a']);
  assert.deepEqual(listOrder([d('a', null), d('b', '2026-12-01T00:00:00Z'), d('c', '2026-11-01T00:00:00Z')], 'closed').map((x) => x.id), ['b', 'c', 'a']);
  // The order asked for is applied; without one, the status decides.
  const e = (id: string, deadline: string | null, publishedAt: string | null) => ({ id, deadline, publishedAt });
  const rowsE = [e('a', '2026-12-01T00:00:00Z', '2026-01-01'), e('b', '2026-11-01T00:00:00Z', '2026-03-01'), e('c', null, null)];
  assert.deepEqual(listOrder(rowsE, 'open', 'deadline-desc').map((x) => x.id), ['a', 'b', 'c']);
  assert.deepEqual(listOrder(rowsE, 'open', 'published-desc').map((x) => x.id), ['b', 'a', 'c']);
  assert.deepEqual(listOrder(rowsE, 'closed', 'deadline-asc').map((x) => x.id), ['b', 'a', 'c']);
  // A failed build is remembered for its TTL only, and is not run again meanwhile.
  let now = 0;
  const failing = new ExportRunner<string>(new TtlCache(1000, 10), new Gate(6), 2, new TtlCache(30_000, 10, () => now));
  let runs = 0;
  const boom = async () => { runs += 1; throw new Error('x'); };
  await assert.rejects(failing.get('k', boom));
  await assert.rejects(failing.get('k', boom));
  assert.equal(runs, 1, 'remembered');
  now = 30_001;
  await assert.rejects(failing.get('k', boom));
  assert.equal(runs, 2, 'forgotten after 30 s');
  console.log('cursor export checks passed');
})();
