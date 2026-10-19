/**
 * Self-check of the content-structure fixes of WP-56 (UX audit T20, T24, C4, C5, C6). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { LONG_TEXT_OVER, fullTextLabel, mergeSameText, textHead } from './long-text';
import { isoDatesToSite } from './format';
import { DESCRIPTION_MAX, TITLE_MAX, trimAtWord } from './seo-trim';
import { GROUP_MIN, groupIssuers, publicPassage, publicRef, ruleSentence, siteDay, withoutAnswerEcho, faqOf } from './readiness';
import { parseCallFilters } from './filters';
import type { RIssuer, RequirementDetail } from './readiness-types';
import mock from './mock/requirements.json';

// T20b / C6: a long text is shown as its first ~600 characters and the whole of it behind a label with its length; a short one is whole.
assert.equal(textHead('short text'), null);
assert.equal(textHead('x'.repeat(LONG_TEXT_OVER)), null);
const long = Array.from({ length: 400 }, (_, i) => `word${i}`).join(' ');
const head = textHead(long)!;
assert.ok(head.length <= 601 && head.endsWith('…') && long.startsWith(head.slice(0, -1)), 'cut at a word, ellipsis marks the cut');
assert.ok(long.split(' ').includes(head.slice(0, -1).split(' ').pop()!), 'the last word is whole');
assert.equal(fullTextLabel('a'.repeat(8591)), 'Show full text, 8,591 characters');

// C6: two rows with the same text are one row; different texts stay as they are.
const same = mergeSameText([
  { label: 'Eligible countries', value: 'Described in section 6 of the call document.' },
  { label: 'Other eligibility conditions', value: 'Described in section 6 of the call document.' },
]);
assert.deepEqual(same, [{ label: 'Eligible countries and other eligibility conditions', value: 'Described in section 6 of the call document.' }]);
assert.equal(mergeSameText([{ label: 'a', value: '1' }, { label: 'b', value: '2' }]).length, 2);

// F-15: a day the source wrote as 2026-12-15 reads like the rest of the site; a non-day is left alone.
assert.equal(isoDatesToSite('Project start 2027-01-04 to 2027-01-11'), 'Project start 4 Jan 2027 to 11 Jan 2027');
assert.equal(isoDatesToSite('Reference 2026-13-45 stays'), 'Reference 2026-13-45 stays');
assert.equal(siteDay('2026-09-07'), '7 Sep 2026');
assert.equal(siteDay('2026-09-07T10:00:00+00:00'), '7 Sep 2026');
assert.equal(siteDay('not a day'), 'not a day');

// C5: titles fit 60 characters with the site template, descriptions 160; a text that fits is unchanged; the cut is at a word.
assert.equal(TITLE_MAX, 46);
assert.equal(trimAtWord('Regulatory tracker', TITLE_MAX), 'Regulatory tracker');
for (const t of ['Requirements for EU defence programmes: NCAGE, PIC, AQAP, export licences', 'Readiness check: may your company take part in EDF, EDIP and SAFE?',
  'Repeat participants of a capability area with no partner from one country']) {
  const out = trimAtWord(t, TITLE_MAX);
  assert.ok(out.length <= TITLE_MAX && out.endsWith('…'), out);
  assert.ok(t.startsWith(out.slice(0, -1)), 'a prefix of the title');
  assert.ok(!/[,:;]…$/.test(out), 'no dangling punctuation before the ellipsis');
}
assert.equal(trimAtWord('Requirements for EU defence programmes: NCAGE, PIC, AQAP, export licences', TITLE_MAX), 'Requirements for EU defence programmes: NCAGE…');
assert.ok(trimAtWord('word '.repeat(100), DESCRIPTION_MAX).length <= DESCRIPTION_MAX);
assert.equal(trimAtWord('a'.repeat(200), 50).length, 50, 'one long word is cut where it stands');

// C4: our working document is not named on a public page.
assert.equal(publicRef('NSPA, quoted in the DefenceGate technical appendix, NCAGE'), 'NSPA');
assert.equal(publicRef('Ekontrol (Bureau Veritas partner, Ukraine), 2026, quoted in the DefenceGate technical appendix'), 'Ekontrol (Bureau Veritas partner, Ukraine), 2026');
assert.equal(publicRef('DefenceGate technical appendix, Participant Register and PIC'), null);
assert.equal(publicRef('Regulation (EU) 2021/697, Article 9'), 'Regulation (EU) 2021/697, Article 9');
assert.equal(publicPassage('[NSPA, quoted in the DefenceGate technical appendix, NCAGE] In accordance with NATO policy.'), '[NSPA] In accordance with NATO policy.');
assert.equal(publicPassage('[DefenceGate technical appendix, Export control] Dual-use falls under 2021/821.'), 'Dual-use falls under 2021/821.');
assert.equal(publicPassage('[Regulation (EU) 2021/697, Article 9] Text.'), '[Regulation (EU) 2021/697, Article 9] Text.');
assert.equal(publicPassage('no label at all'), 'no label at all');
// the page text of a requirement never carries "technical appendix" or a code of ours, whatever the stored reference says
for (const r of Object.values(mock.requirements) as { source: { ref: string | null; text: string | null } }[]) {
  const shown = [publicRef(r.source.ref) ?? '', ...(r.source.text ?? '').split('\n\n').map(publicPassage)].join(' ');
  assert.ok(!/technical appendix/i.test(shown), shown.slice(0, 120));
}

// M-11: a static page does not repeat an answer the visitor never gave.
assert.equal(
  withoutAnswerEcho('You said you move dual-use items to other EU countries. Such a transfer needs an authorisation only for items listed in Annex IV.'),
  'Such a transfer needs an authorisation only for items listed in Annex IV.');
assert.equal(withoutAnswerEcho('Recipients must be established in the Union.'), 'Recipients must be established in the Union.');
assert.equal(ruleSentence({ info: 'You said you are a SEAP.' }), '');

// M-9: the NCAGE issuers are one grouped list; every row's country is kept.
const ncage = (mock.requirements as unknown as Record<string, { issuers: RIssuer[] }>)['REQ-NCAGE'];
const { singles, groups } = groupIssuers(ncage.issuers);
assert.equal(singles.length + groups.reduce((n, g) => n + g.countries.length, 0), ncage.issuers.length, 'no row is lost');
assert.ok(groups.length === 2 && groups[0].countries.length === 31 && groups[1].countries.length === 19, JSON.stringify(groups.map((g) => g.countries.length)));
assert.deepEqual(singles.map((s) => s.country), ['*', 'ES', 'UA'], 'the row for every country first, then by country name');
for (const g of groups) assert.deepEqual([...g.countries].sort((a, b) => a.localeCompare(b, 'en')), g.countries, 'countries in name order');
assert.ok(groups.every((g) => g.countries.length >= GROUP_MIN));
const two: RIssuer[] = [0, 1].map((i) => ({ country: i ? 'FR' : 'DE', name: 'Same body', url: null, notes: 'same', verificationStatus: 'U' as const }));
assert.equal(groupIssuers(two).groups.length, 0, 'fewer than three identical rows stay single rows');
// the question about issuers is answered with the same grouping, once per group, not once per country
const faqAnswer = faqOf({ ...(mock.requirements as unknown as Record<string, RequirementDetail>)['REQ-NCAGE'], kind: 'document', mandatoryFor: null })[0].a;
assert.ok(faqAnswer.length < 4000 && (faqAnswer.match(/National codification bureau \(NCB\) of the country/g) ?? []).length === 2, `${faqAnswer.length}`);

// T24: `?programme=edf` works like `EDF`.
assert.deepEqual(parseCallFilters({ programme: 'edf' }).programme, ['EDF']);
assert.deepEqual(parseCallFilters({ programme: 'EDF,horizon' }).programme, ['EDF', 'HORIZON']);
assert.equal(parseCallFilters({ programme: 'nonsense' }).programme, undefined);

console.log('wp56.check ok');
