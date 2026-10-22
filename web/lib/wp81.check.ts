/**
 * Self-check of WP-81 (the sum of contract values per supplier, owner decision of 22 October 2026): the words of the collapsed
 * "Contract values" block: per currency, never converted; lot estimates flagged; how many state no value, and how many of those
 * name several winners; the rules line says single winner, PLACSP adds none, each contract once, framework ceilings.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { allWinnersLabel, approachOthersLine, otherWinnersLine, winnersHref, type DemandCountry } from './demand';
import { sumLines, VALUE_RULES, withoutValueLine, type ValueTotals } from './value-totals';

const none: ValueTotals = { byCurrency: [], of: 3, withoutValue: 3, shared: 0 };
assert.deepEqual(sumLines(none, 'contract'), []);
assert.equal(withoutValueLine(none, 'contract'), '3 of 3 contracts state no value for this company alone.');

const mixed: ValueTotals = {
  byCurrency: [{ currency: 'EUR', amount: 3000.4, count: 2, lotEstimates: 1 }, { currency: 'PLN', amount: 500, count: 1, lotEstimates: 0 }],
  of: 30, withoutValue: 27, shared: 4,
};
assert.deepEqual(sumLines(mixed, 'contract'), [
  'EUR 3,000 over 2 contracts (1 of them is the sum of the lots’ estimated values, not a stated total)',
  'PLN 500 over 1 contract',
]);
assert.equal(withoutValueLine(mixed, 'notice'), '27 of 30 notices state no value for this company alone; 4 of them name several winners.');
assert.equal(sumLines({ ...mixed, byCurrency: [{ currency: 'EUR', amount: 10, count: 1, lotEstimates: 1 }] }, 'contract')[0],
  'EUR 10 over 1 contract (it is the sum of the lots’ estimated values, not a stated total)');
assert.equal(sumLines({ ...mixed, byCurrency: [{ currency: 'EUR', amount: 10, count: 2, lotEstimates: 2 }] }, 'contract')[0],
  'EUR 10 over 2 contracts (all are the sum of the lots’ estimated values, not a stated total)');
assert.equal(withoutValueLine({ byCurrency: [], of: 1, withoutValue: 1, shared: 1 }, 'contract'),
  '1 of 1 contract states no value for this company alone; it names several winners.');
assert.equal(withoutValueLine({ ...mixed, withoutValue: 2, shared: 2 }, 'contract'),
  '2 of 30 contracts state no value for this company alone; they name several winners.');
assert.equal(withoutValueLine({ ...mixed, withoutValue: 0, shared: 0 }, 'contract'), null);

for (const said of ['per currency, never converted', 'names this one winner', 'without VAT', 'PLACSP values are the awarded amounts',
  'counted once', 'PLACSP’s awarded amount, else TED’s value', 'framework ceilings']) {
  assert.ok(VALUE_RULES.includes(said), said);
}
// ---------------------------------------------------------------- every legal-entity winner named (scope addition, owner "да", 22 October 2026)
// The API answers kMin 1: no winner is held back for having few awards, so the country line speaks of the end of the list only. The demo
// answer (lib/mock/demand.json) is production's of 22 October under the old kMin 3, and its words stay those of that rule (wp66/wp80 checks).
const country = { otherWinners: { winners: 7, awards: 9 } } as unknown as DemandCountry;
assert.equal(otherWinnersLine(country, 1), '7 other winners (9 awards) not listed here: the list shows the ten with the most awards per country, and the report names them all under Who to approach.');
assert.match(otherWinnersLine(country, 3) ?? '', /named only with at least 3 awards/);
assert.equal(approachOthersLine({ winners: [], below: { winners: 0, awards: 0 }, more: { winners: 0, awards: 0 } }, 1), null);

// the link under a list that stops before the end (follow-up: nothing hidden)
assert.equal(allWinnersLabel(496), 'All 496 winners for these codes');
assert.equal(allWinnersLabel(1, 'Spain'), 'All 1 winner in Spain for these codes');
assert.equal(winnersHref(), '/readiness/supplier/winners');
assert.equal(winnersHref('ES'), '/readiness/supplier/winners?country=ES');

// the mosaic rule's words stay out: no ranking, no share, no sole source
assert.doesNotMatch(VALUE_RULES + sumLines(mixed, 'contract').join(' '), /rank|share of|market share|sole source|single point/i);
