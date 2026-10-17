/**
 * Self-check of the words and formats of the readiness pages (WP-29). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { daysRange, faqOf, formatDays, formatRange, isoDay, originWords, requirementCode, requirementSlug } from './readiness';
import type { RMoney, RequirementDetail, RSource } from './readiness-types';

const usd: RMoney = { min: 17000, max: 48000, currency: 'USD', basis: 'vendor_range', text: 'USD 17,000-48,000', alt: null, label: 'vendor range, not a benchmark' };
const free: RMoney = { min: 0, max: 0, currency: null, basis: 'free', text: 'Free', alt: null, label: null };

// Money is shown in the currency the source used, never converted; a missing figure says so.
assert.equal(formatRange(usd), 'USD 17,000 to 48,000');
assert.equal(formatRange(free), 'Free');
assert.equal(formatRange(null), 'Not stated in the sources');
assert.equal(formatRange({ ...usd, min: null }), 'Not stated in the sources');
assert.equal(formatRange({ ...usd, min: 5, max: 5 }), 'USD 5');

// Durations: the source's own words when it has them, else days or months.
assert.equal(formatDays({ min: 90, max: 240, text: '3-8 months', note: null }), '3-8 months');
assert.equal(formatDays({ min: 5, max: 20, text: null, note: null }), '5 to 20 days');
assert.equal(formatDays(null), 'Not stated in the sources');
assert.equal(daysRange(0, 0), 'immediate');
assert.equal(daysRange(90, 240), '3 to 8 months');
assert.equal(daysRange(90, 90), '3 months');
assert.equal(daysRange(10, 90), '10 to 90 days');

// A requirement page address is the code without its prefix, lower case; and back.
assert.equal(requirementSlug('REQ-AQAP2110'), 'aqap2110');
assert.equal(requirementSlug('REQ-FSC-ES'), 'fsc-es');
assert.equal(requirementCode('aqap2110'), 'REQ-AQAP2110');
assert.equal(requirementCode('req-ncage'), 'REQ-NCAGE');
assert.equal(requirementCode('../etc'), null);
assert.equal(requirementCode('a'.repeat(40)), null);

assert.equal(isoDay('2026-10-17T12:00:00+00:00'), '2026-10-17');

const notes: RSource = { url: 'https://example.test', ref: 'r', text: '[r] t', origin: 'notes', verificationStatus: 'V', lastReviewed: '2026-09-07' };
assert.ok(originWords(notes).includes('research notes'));
assert.ok(originWords({ ...notes, origin: 'primary' }).includes('Official Journal'));

// The questions a requirement page answers are built from its data, and say what was not collected.
const req = {
  code: 'REQ-X', name: 'Thing', kind: 'document', cost: usd, days: { min: 90, max: 240, text: '3-8 months', note: null },
  issuers: [{ country: 'ES', name: 'Body ES', url: null, notes: null, verificationStatus: 'S' }, { country: '*', name: 'Everywhere body', url: null, notes: null, verificationStatus: 'V' }],
  mandatoryFor: 'contracts that name it',
} as unknown as RequirementDetail;
const faq = faqOf(req);
assert.equal(faq.length, 4);
assert.ok(faq[0].a.includes('Everywhere body (the same body for every country)') && faq[0].a.includes('Spain: Body ES') && faq[0].a.includes('not been collected'));
assert.ok(faq[1].a.includes('vendor range, not a benchmark'));
assert.equal(faq[2].a, '3-8 months.');
assert.deepEqual(faqOf({ ...req, issuers: [], cost: null, days: null, mandatoryFor: null } as RequirementDetail).map((f) => f.a),
  ['The issuing body has not been collected for any country.', 'No cost is stated in the sources used.', 'No duration is stated in the sources used.']);
assert.deepEqual(faqOf({ ...req, kind: 'rule', mandatoryFor: null } as RequirementDetail), []);
console.log('readiness.check ok');
