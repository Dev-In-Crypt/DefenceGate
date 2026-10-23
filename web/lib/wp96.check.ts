/**
 * Self-check of WP-96 (persona round of 23 October 2026, A2: entities, counts, links), the pure parts of the web:
 *   5. raw procedure and legal-basis codes of the German notice service and of eForms in words
 *   7. the calendar and its file say how many open tenders state no deadline; /data's usual month is the last year's
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { calendarCounts, withoutDeadlineLine } from './calendar-counts';
import { buildIcs } from './ics';
import { gapSentence } from './source-status';
import { legalBasisLabel, procedureLabel } from './taxonomy';

// ---- 5. codes in words
assert.equal(procedureLabel('De-open'), 'Open procedure (German national rules)');
assert.equal(procedureLabel('De-comp-wo-call'), 'Restricted procedure without a call for competition (German national rules)');
assert.equal(procedureLabel('neg-wo-call'), 'Negotiated procedure without prior publication');
assert.equal(procedureLabel('Open procedure'), null, 'an English name is shown as it is');
assert.equal(legalBasisLabel('de-uvgo'), 'UVgO (German rules for supplies and services below the EU thresholds)');
assert.equal(legalBasisLabel('DE-VSVGV'), 'VSVgV (German defence and security procurement regulation)');
assert.equal(legalBasisLabel('de-xyz'), 'German national procurement rules (XYZ)');
assert.equal(legalBasisLabel('32009L0081'), 'Directive 2009/81/EC (defence and security procurement)');

// ---- 7. the calendar names the open tenders without a deadline (DE: 57 of the list's 231)
const p = { kind: 'tenders' as const, countries: ['DE'], tender: {} };
const lines = calendarCounts({ tendersOk: true, callsOk: true, tendersHeld: 174, longRunning: 2, withoutDeadline: 57, openCalls: [] }, p,
  { tenders: 172, calls: 0 }, '2026-10-23');
assert.match(lines[0].text, / 57 open tenders state no deadline: the tenders list shows them, the calendar cannot\.$/);
assert.equal(withoutDeadlineLine(1), '1 open tender states no deadline: the tenders list shows it, the calendar cannot.');
assert.equal(withoutDeadlineLine(0), '');
const none = calendarCounts({ tendersOk: true, callsOk: true, tendersHeld: 10, longRunning: 0, openCalls: [] }, p, { tenders: 10, calls: 0 }, '2026-10-23');
assert.doesNotMatch(none[0].text, /no deadline/);
const ics = buildIcs([], new Date('2026-10-23T08:00:00Z'), { withoutDeadline: 76 });
assert.match(ics.replace(/\r\n /g, ''), /76 open tenders state no deadline and are not in it\\; the tenders list has them\./);

// ---- 7. /data: the usual month is the last twelve months' (PLACSP said "about 21" of 41,142 notices)
assert.equal(
  gapSentence({ name: 'Spain (PLACSP)', heldFrom: '2015-01-02', heldTo: '2026-10-22', monthlyMedian: 950, gapMonths: ['2015-02', '2015-03'] }),
  'Spain (PLACSP): publication dates 2 Jan 2015 to 22 Oct 2026. In the last 12 months the usual month held about 950 notices. Months with fewer than half of that: Feb to Mar 2015.',
);

console.log('wp96 checks passed');
