/**
 * Self-check of the export helpers (CSV cells, calendar-file text). Not part of the app and not imported by it.
 * Run from web/:  npx tsc lib/export.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/export.check.js
 */
import assert from 'node:assert/strict';
import { csvCell, isMidnight, isoUtc, toCsv } from './csv';
import { foldLine, icsText } from './ics';
import { cpvPrefix } from './cpv';

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

console.log('export checks passed');
