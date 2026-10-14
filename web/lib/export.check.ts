/**
 * Self-check of the export helpers (CSV cells, calendar-file text). Not part of the app and not imported by it.
 * Run from web/:  npx tsc lib/export.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/export.check.js
 */
import assert from 'node:assert/strict';
import { csvCell, isMidnight, isoUtc, toCsv } from './csv';
import { foldLine, icsText } from './ics';
import { cpvPrefix } from './cpv';
import { ExportRunner, Gate, TtlCache, tooBroad } from './export-cache';

// Spreadsheet formulas are defused, ordinary text is not touched.
for (const bad of ['=SUM(A1)', '+1', '-1+2', '@cmd', '\tx', '\rx']) assert.ok(csvCell(bad).replace(/^"/, '').startsWith("'"), bad);
assert.equal(csvCell('Dostawa'), 'Dostawa');
assert.equal(csvCell(-5), '-5');
assert.equal(csvCell('a,b'), '"a,b"');
assert.equal(csvCell('say "hi"'), '"say ""hi"""');
assert.equal(csvCell('line\nbreak'), 'line break');
assert.equal(csvCell(null), '');
assert.equal(toCsv(['a', 'b'], [['1', '=2']]), '﻿a,b\r\n1,\'=2\r\n');

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
