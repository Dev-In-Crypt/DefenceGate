/**
 * Self-check of WP-59 (fixes from the content re-audit): plurals, titles and descriptions cut where a phrase ends, quotes that
 * start inside a sentence. Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { plural } from './format';
import { DESCRIPTION_MAX, TITLE_MAX, trimAtPhrase } from './seo-trim';
import { buildMetadata, listViewTitle } from './seo';
import { daysRange, publicPassage } from './readiness';

// NEW-8: one helper for the noun of a count.
assert.equal(`1 ${plural(1, 'factsheet')}`, '1 factsheet');
assert.equal(`0 ${plural(0, 'factsheet')}`, '0 factsheets');
assert.equal(`2 ${plural(2, 'country', 'countries')}`, '2 countries');
assert.equal(daysRange(1, 1), '1 day');
assert.equal(daysRange(5, 5), '5 days');

// NEW-5: a title or description that does not fit ends where a phrase ends, not mid-phrase.
const titles: [string, string][] = [
  ['Requirements for EU defence programmes: NCAGE, PIC, AQAP, export licences', 'Requirements for EU defence programmes'],
  ['Readiness check: may your company take part in EDF, EDIP and SAFE?', 'Readiness check'],
  ['ISO 9001 quality management certificate: who issues it, cost and time', 'ISO 9001 quality management certificate'],
  ['PIC (Participant Identification Code): who issues it, cost and time', 'PIC (Participant Identification Code)'],
  ['HSEM facility security clearance (Spain): who issues it, cost and time', 'HSEM facility security clearance (Spain)'],
];
for (const [full, want] of titles) {
  const out = trimAtPhrase(full, TITLE_MAX, 12);
  assert.equal(out, want);
  assert.ok(out.length <= TITLE_MAX && !out.endsWith('…'));
}
assert.equal(trimAtPhrase('Regulatory tracker', TITLE_MAX, 12), 'Regulatory tracker', 'a title that fits is unchanged');
// A quoted search is the view itself: it is cut at a word, never dropped at its colon.
assert.equal(trimAtPhrase('Tenders, page 2: “very long search words that go on and on”', TITLE_MAX, 12), 'Tenders, page 2: “very long search words that…');
// No phrase end far enough in: cut at a word, with the ellipsis, as before.
assert.equal(trimAtPhrase('Glossary of defence procurement and funding terms', TITLE_MAX, 12), 'Glossary of defence procurement and funding…');

const alerts = 'E-mail alerts and saved searches are being prepared and are not open yet. What works today without an account: filters in the address, CSV, a deadline calendar file and a feed of what changed.';
assert.equal(trimAtPhrase(alerts, DESCRIPTION_MAX, 40, '.'), 'E-mail alerts and saved searches are being prepared and are not open yet.');
const terms = 'The terms on which DefenceGate is provided: what the service is, that the original source is authoritative, acceptable use, corrections and removal, and limits of liability.';
assert.equal(trimAtPhrase(terms, DESCRIPTION_MAX, 40, '.'), 'The terms on which DefenceGate is provided.');
const regulation = 'Changes in the rules that matter to a defence supplier (SAFE, EDIP, the Ukraine Support Instrument, the European Defence Fund, the defence procurement directive and export control).';
assert.equal(trimAtPhrase(regulation, DESCRIPTION_MAX, 40, '.'), 'Changes in the rules that matter to a defence supplier.');
const requirements = 'What separates a company from taking part in EDF, EDIP, SAFE and NATO supply: each requirement, who issues it (in the countries covered so far), what it costs and how long it takes, with the source and the date it was last reviewed.';
assert.equal(trimAtPhrase(requirements, DESCRIPTION_MAX, 40, '.'), 'What separates a company from taking part in EDF, EDIP, SAFE and NATO supply.', 'a colon before a bracket');
for (const t of [alerts, terms, regulation, requirements, 'word '.repeat(100)]) assert.ok(trimAtPhrase(t, DESCRIPTION_MAX, 40, '.').length <= DESCRIPTION_MAX);
// The metadata helper uses it.
assert.equal(buildMetadata({ title: titles[0][0], description: alerts, path: '/x' }).title, titles[0][1]);
assert.equal(buildMetadata({ title: titles[0][0], description: alerts, path: '/x' }).description, 'E-mail alerts and saved searches are being prepared and are not open yet.');

// NEW-6: a quote whose label was its subject starts with an ellipsis; a quoted table row has no pipes.
assert.equal(publicPassage('[DefenceGate technical appendix, Participant Register and PIC] register the organisation on the Portal.'), '…register the organisation on the Portal.');
assert.equal(publicPassage('[DefenceGate technical appendix, AQAP editions] AQAP 2310 | Edition B Version 2, January 2022 | Quality management'),
  'AQAP 2310 · Edition B Version 2, January 2022 · Quality management');
assert.equal(publicPassage('[Regulation (EU) 2021/697, Article 9] Text.'), '[Regulation (EU) 2021/697, Article 9] Text.', 'a sentence start is kept');

// Data-pages re-audit NEW-6: an unknown country code is not echoed as a country in a title.
assert.equal(listViewTitle('Defence supplier map', 'Supplier map', { countries: ['XX'], filters: 1 }), 'Supplier map (filtered)');
assert.equal(listViewTitle('Defence supplier map', 'Supplier map', { countries: ['DE'], filters: 1 }), 'Supplier map in Germany');

console.log('wp59 checks passed');
