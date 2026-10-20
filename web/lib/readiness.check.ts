/**
 * Self-check of the words and formats of the readiness pages (WP-29). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { PROGRAMME_NAME, joinWords, programmeName, OUTCOME_WORD, VERDICT_MEANING, VERDICT_WORD, daysRange, faqOf, formatDays, formatRange, isoDay, originWords, requirementCode, requirementSlug, ruleSentence, statusWords } from './readiness';
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
assert.equal(daysRange(0, 0), 'no time needed', 'U8: never "0 to 0 days"');
assert.equal(formatDays({ min: 0, max: 0, text: 'immediate', note: null }), 'immediate', 'the source own word wins');
assert.equal(formatDays({ min: 0, max: 0, text: null, note: null }), 'no time needed');
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

// D8: a line taken from the research notes is never said to have been fetched; a line checked against the Official Journal is.
assert.ok(!statusWords('V', 'notes').includes('page was fetched'));
assert.ok(statusWords('V', 'notes').includes('not checked again on this site'));
assert.ok(statusWords('V', 'primary').includes('Official Journal'));
assert.equal(statusWords('S', 'notes'), 'Seen in search results, not fetched directly.');
assert.ok(statusWords('U', 'primary').startsWith('Unverified'));

// D7: a requirement page prints what a rule asks, never the second-person "not met" sentence.
assert.equal(ruleSentence({ requires: 'Recipients must be established in the Union.', not_met: 'Your company is controlled from a third country.' }), 'Recipients must be established in the Union.');
assert.equal(ruleSentence({ info: 'AQAP is a contract matter.' }), 'AQAP is a contract matter.');
assert.equal(ruleSentence({ not_met: 'Your company is controlled from a third country.' }), '');

// D3: a registration that is missing is "Obtain first", not "Blocked", and "Eligible" says what it does not cover.
assert.equal(VERDICT_WORD.obtain, 'Obtain first');
assert.equal(OUTCOME_WORD.to_obtain, 'To obtain');
assert.ok(VERDICT_MEANING.obtain.includes('registration you can obtain'));
assert.ok(VERDICT_MEANING.eligible.includes('exclusion criteria') && VERDICT_MEANING.eligible.includes('conditions each call sets'));

// The questions a requirement page answers are built from its data, and say what was not collected.
const req = {
  code: 'REQ-X', name: 'Thing', kind: 'document', cost: usd, days: { min: 90, max: 240, text: '3-8 months', note: null },
  issuers: [{ country: 'ES', name: 'Body ES', url: null, notes: null, verificationStatus: 'S' }, { country: '*', name: 'Everywhere body', url: null, notes: null, verificationStatus: 'V' }],
  mandatoryFor: 'contracts that name it',
} as unknown as RequirementDetail;
const faq = faqOf(req);
assert.equal(faq.length, 4);
// WP-59 (re-audit NEW-7): a row for every country next to country rows is "every other country", and nothing is then "not collected".
assert.equal(faq[0].a, 'Spain: Body ES. Every other country: Everywhere body.');
assert.equal(faqOf({ ...req, issuers: [req.issuers[1]] } as RequirementDetail)[0].a, 'Everywhere body (the same body for every country).');
assert.equal(faqOf({ ...req, issuers: [req.issuers[0]] } as RequirementDetail)[0].a, 'Spain: Body ES. The body has not been collected for the countries not listed.');
assert.ok(faq[1].a.includes('vendor range, not a benchmark'));
assert.equal(faq[2].a, '3-8 months.');
assert.deepEqual(faqOf({ ...req, issuers: [], cost: null, days: null, mandatoryFor: null } as RequirementDetail).map((f) => f.a),
  ['The issuing body has not been collected for any country.', 'No cost is stated in the sources used.', 'No duration is stated in the sources used.']);
assert.deepEqual(faqOf({ ...req, kind: 'rule', mandatoryFor: null } as RequirementDetail), []);
// U13: the stored keys of the programmes are never shown as they are.
assert.equal(programmeName('GENERAL'), 'the general requirements');
assert.equal(programmeName('NATO-SUPPLY'), 'NATO and NSPA supply');
assert.equal(programmeName('EDIP-USI'), 'EDIP Ukraine Support Instrument');
assert.equal(programmeName('NEW-ONE'), 'NEW-ONE', 'an unknown key is shown as it is');
for (const k of ['EDF', 'EDIP', 'EDIP-USI', 'SAFE', 'NATO-SUPPLY', 'GENERAL']) assert.ok(PROGRAMME_NAME[k], k);
assert.equal(joinWords(['a']), 'a');
assert.equal(joinWords(['a', 'b']), 'a and b');
assert.equal(joinWords(['a', 'b', 'c']), 'a, b and c');
// V2-B1: a rule quoted from a call document says so; it is neither "the Official Journal" nor "the research notes".
assert.ok(originWords({ ...notes, origin: 'call_document' }).includes('call document'));
assert.ok(!originWords({ ...notes, origin: 'call_document' }).includes('research notes'));
assert.ok(statusWords('V', 'call_document').includes('call document') && !statusWords('V', 'call_document').includes('Official Journal text of the regulation'));
console.log('readiness.check ok');
