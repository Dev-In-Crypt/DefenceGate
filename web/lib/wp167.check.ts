// WP-167 self-check: Ukraine's EDF association in force since 16 October 2026 (the call check, the sentence, the old reason name), and the
// call document's budget total next to the portal's figure. Run: node scripts/run-checks.mjs
import assert from 'node:assert/strict';
import { EDF_UA_AREA, EDF_UA_BEFORE, EDF_UA_YES, USI_AREA_QUOTE, check, countryStatus, type EligibilityFact } from './eligibility-check';
import { documentBudgetLine, millions } from './format';
import { EDF_IN_FORCE, EDF_IN_FORCE_URL, beforeAssociation } from './ukraine';

// the call check: an open EDF call whose document is open to the associated countries is open to a Ukrainian company, with the
// Commission's sentence; a call that closed before 16 October 2026 keeps the question (its document said "pending"); Norway untouched
const fact: EligibilityFact = { value: 'listed EEA countries and countries associated to the EDF Programme', note: null, quote: '', confidence: 1, scope: 'call_document' };
const ctx = { programme: 'EDF', topic: 'EDF-2027-DA-X' };
assert.deepEqual(countryStatus(fact, 'UA', ctx), { verdict: 'yes', reason: EDF_UA_YES });
assert.ok(EDF_UA_YES.includes(EDF_IN_FORCE), 'the Commission, word for word');
assert.deepEqual(countryStatus(fact, 'UA', { ...ctx, ukraineBeforeAssociation: true }), { verdict: 'check', reason: EDF_UA_BEFORE });
assert.equal(countryStatus(fact, 'NO', { ...ctx, ukraineBeforeAssociation: true }).verdict, 'yes');
// the EDIP Programme is not touched: Ukraine is not one of its associated countries
assert.equal(countryStatus({ ...fact, value: 'EU Member States and EDIP associated countries' }, 'UA', { programme: 'EDF', topic: 'EDF-EDIP-P-2027-FNLC-CPA-X' }).verdict, 'no');
const line = check({ eligible_countries: fact }, { country: 'UA', orgType: '', hasPartners: '', controlledAbroad: '' }, ctx).lines.find((l) => l.key === 'country')!;
assert.equal(line.verdict, 'yes');

// a Ukrainian company in a non-government controlled area: a check with the USI call documents' sentence, never a yes (coordinator, 31 Oct)
const occupied = check({ eligible_countries: fact }, { country: 'UA', orgType: '', hasPartners: '', controlledAbroad: '', more: { uaOccupied: 'yes' } } as Parameters<typeof check>[1], ctx).lines;
assert.deepEqual(occupied.find((l) => l.key === 'territory'), { key: 'territory', label: 'Non-government controlled areas', verdict: 'check', reason: EDF_UA_AREA, quote: USI_AREA_QUOTE });
assert.notEqual(check({ eligible_countries: fact }, { country: 'UA', orgType: '', hasPartners: '', controlledAbroad: '', more: { uaOccupied: 'yes' } } as Parameters<typeof check>[1], ctx).verdict, 'yes');

// the reason names: the new one and the old one (until the flags are re-run) both mean "closed before the day"
assert.ok(beforeAssociation('edf_closed_before_association') && beforeAssociation('edf_association_unconfirmed'));
assert.ok(!beforeAssociation('edf_association') && !beforeAssociation(undefined));
assert.ok(EDF_IN_FORCE_URL.startsWith('https://defence-industry-space.ec.europa.eu/') && EDF_IN_FORCE_URL.endsWith('-2026-10-16_en'));

// the budget line: the two Ukraine Support Instrument calls
assert.equal(documentBudgetLine({ amount: 184_500_000, votedEu: 180_000_000, currency: 'EUR' }),
  'Call document total: EUR 184.5 million, including EUR 180 million from the voted EU budget.');
assert.equal(documentBudgetLine({ amount: 82_000_000, votedEu: 80_000_000, currency: 'EUR' }),
  'Call document total: EUR 82 million, including EUR 80 million from the voted EU budget.');
assert.equal(documentBudgetLine({ amount: 422_000_000, votedEu: null, currency: 'EUR' }), 'Call document total: EUR 422 million.');
assert.equal(millions({ amount: 1_234_567, currency: 'EUR' }), 'EUR 1,234,567', 'not round: the amount in full');
console.log('wp167 checks passed');
