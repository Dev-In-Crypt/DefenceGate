/**
 * Self-check of the display of a quoted sentence (U13, 18 October 2026). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { cleanQuote } from './quote';

// The footnote numbers the PDF text glues to a word (two of the three seen on call 131 of 18 October 2026).
assert.equal(cleanQuote('under Horizon Europe202 and the programme.'), 'under Horizon Europe and the programme.');
assert.equal(cleanQuote('a private investor201, or a fund'), 'a private investor, or a fund');
assert.equal(cleanQuote('as defined in the Annex to Recommendation 2003/361/EC.'), 'as defined in the Annex to Recommendation 2003/361/EC.', 'a real number is kept');
// A real token is never cut: a code with digits, a year, a one-digit footnote, a number set apart by spaces.
for (const keep of ['H2020 and FP7', 'ISO9001 certified', 'AQAP2110', 'Regulation (EU) 2021/697', 'in 2024.', 'CO2 limits', 'Article 5(1)', 'small mid-caps 196 established', 'a 35 % limit']) {
  assert.equal(cleanQuote(keep), keep, keep);
}
// The stored quote is not touched: only the text handed to the page.
const stored = 'Horizon Europe202';
assert.equal(cleanQuote(stored), 'Horizon Europe');
assert.equal(stored, 'Horizon Europe202');
console.log('quote.check ok');
