/**
 * Self-check of the QA fixes of 12 October 2026 (names, basis chips, change values, source status, list
 * parameters, call deadlines, calendar helpers, export cache). Not part of the app and not imported by it.
 * Run from web/:  npx tsc lib/ui.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/ui.check.js
 */
import assert from 'node:assert/strict';
import { displayName, upperShare } from './display-name';
import { CONFIDENCE_HREF, basisChips, clearanceView, confidenceCell, confidenceView, militaryCodeChip, scopeGroupNote, subcontractingView } from './tender-basis';
import { formatChangeValue } from './change-format';
import { gapSentence, heldSpan, listUpdatedAt, minimumMet, monthRanges, sourceDisplay, sourceFreshness } from './source-status';
import { barLayout, daysText, monthLabel, niceMax, percentText, shareOf } from './market';
import { cpvGroupName, cpvGroupTitle, cpvName } from './cpv';
import { defaultTenderSort, ignoredFilters, isDay, lastPage, parseTenderFilters, toTenderQuery } from './filters';
import { LANGUAGES, TENDER_SCOPES, languageName, legalBasisLabel, procedureLabel } from './taxonomy';
import { callStatusKind, getCallDeadline, getDeadline } from './deadline';
import { isPlaceholderAmount, repeatedCallBudgets } from './format';
import { isLongRunning, sourceStatusWord } from './tender-status';
import { truncationRow } from './csv';
import { pageOf, resolveMonth, truncateTitle } from './calendar-view';
import { ExportRunner, Gate, TtlCache, exportCap } from './export-cache';

// ---- Names: capitals are shown as words, in the UI only ----
assert.equal(displayName('MINISTRSTVO ZA OBRAMBO', 'title'), 'Ministrstvo za Obrambo');
assert.equal(displayName('MINISTRSTVO ZA OBRAMBO'), 'Ministrstvo za obrambo');
assert.equal(displayName('KOMENDA GŁÓWNA POLICJI', 'title'), 'Komenda Główna Policji');
assert.equal(displayName('Dostawa sprzętu medycznego'), 'Dostawa sprzętu medycznego');          // not shouting: left alone
assert.equal(displayName('DOSTAWA sprzętu medycznego'), 'DOSTAWA sprzętu medycznego');          // under 60% upper case
assert.equal(displayName('MARCHE MINARM/DGA/DO/S2A'), 'Marche MINARM/DGA/DO/S2A');                // a slash keeps the token
assert.equal(displayName('SYSTEME S2A POUR LA MARINE'), 'Systeme S2A pour la marine');            // a code with digits stays
assert.equal(displayName('S2A'), 'S2A');
assert.equal(displayName('NATO SUPPORT AND PROCUREMENT AGENCY (NSPA)'), 'NATO support and procurement agency (NSPA)');
assert.equal(displayName('MOD AND EDA FRAMEWORK FOR EDF AND EDIP'), 'MOD and EDA framework for EDF and EDIP');
assert.equal(displayName('BAAINBW BEREICH TED'), 'BAAINBw bereich TED');
assert.equal(displayName('PHASE II OF THE CIVIL PROGRAMME'), 'Phase II of the civil programme');   // CIVIL is a word, II a numeral
assert.equal(displayName('PHASE I SUPPLY'), 'Phase I supply');
assert.equal(displayName('DOSTAWA I MONTAŻ'), 'Dostawa i montaż');                                // Polish "and" is not a numeral
assert.equal(displayName('DIRECTION GENERALE DE L\'ARMEMENT', 'title'), 'Direction Generale de L\'Armement');
assert.equal(displayName('F-35 SUSTAINMENT'), 'F-35 sustainment');
// An identifier keeps its capitals, and so does a code between dashes; the stretch after a dash opens a sentence.
// (Was "... - bnt - assistance a ..." until site-qa2: a code lower-cased, "round-1 defect 12".)
assert.equal(displayName("2024-ESID-TLN-0046 - BNT - ASSISTANCE A MAITRISE D'OUVRAGE"), "2024-ESID-TLN-0046 - BNT - Assistance a maitrise d'ouvrage");
assert.equal(displayName('EIC STEP Scale Up'), 'EIC STEP Scale Up');                                  // two acronyms in a cased title
assert.equal(displayName('France - honey - FOURNITURE DE MIEL ET PATE A TARTINER CACAO'), 'France - honey - Fourniture de miel et pate a tartiner cacao');
assert.equal(displayName('EIC STEP SCALE UP'), 'EIC step scale up');                                 // all capitals: the known acronym stays
assert.equal(displayName('AMOA_MAYOTTE_LIIC'), 'AMOA_MAYOTTE_LIIC');                            // a file-like name is left as published
assert.equal(displayName(''), '');
assert.ok(upperShare('ABC def') > 0.4 && upperShare('ABC def') < 0.6);
assert.equal(upperShare('1234'), 0);

// ---- Why a notice is listed: the signals, never a generic "Defence notice" ----
assert.deepEqual(basisChips({ legalBasis: '32009L0081', scope: 'core' }), ['Defence directive (2009/81/EC)']);
assert.deepEqual(basisChips({ legalBasis: '2009/81/EC', scope: 'core' }), ['Defence directive (2009/81/EC)']);
assert.deepEqual(basisChips({ legalBasis: '32014L0024', scope: 'core', buyerClass: 'fire_rescue' }), ['Military product code (CPV)', 'Fire and rescue body']);
assert.deepEqual(
  basisChips({ scope: 'supply', buyerClass: 'defence', dualUse: true, securityClearance: true }),
  ['Defence buyer', 'Defence body', 'Dual-use / security', 'Security-clearance field present'],
);
assert.deepEqual(basisChips({ scope: 'core', buyerClass: 'other' }), ['Military product code (CPV)']);
assert.ok(!basisChips({ scope: 'core', legalBasis: '32009L0081', buyerClass: 'security' }).some((c) => /Defence notice/.test(c)));

// ---- A signal we never read is not "not found" ----
const tedNew = { source: { sourceId: 'ted' }, publishedAt: '2026-09-01T00:00:00Z' };
assert.equal(clearanceView({ ...tedNew, securityClearance: false }).text, 'Not detected');
assert.equal(subcontractingView({ ...tedNew, subcontracting: false }).text, 'Not detected');
assert.equal(clearanceView({ source: { sourceId: 'fr_boamp' }, publishedAt: '2026-09-01T00:00:00Z', securityClearance: false }).text, 'Not read from this source');
assert.equal(clearanceView({ source: { sourceId: 'ted' }, publishedAt: '2021-05-01T00:00:00Z', securityClearance: false }).text, 'Not read from this source');
assert.equal(subcontractingView({ source: { sourceId: 'pl_ezam' }, publishedAt: null, subcontracting: false }).text, 'Not read from this source');
assert.equal(clearanceView({ ...tedNew, securityClearance: true }).text, 'Field present in the notice');
assert.ok(clearanceView({ ...tedNew, securityClearance: true }).hint);
assert.equal(subcontractingView({ ...tedNew, subcontracting: true }).text, 'Mentioned in the notice');

// ---- The data time of a list is shown only when the API sends it ----
assert.equal(listUpdatedAt({ meta: { updatedAt: '2026-10-13T15:16:44Z' } }), '2026-10-13T15:16:44Z');
assert.equal(listUpdatedAt({}), null);
assert.equal(listUpdatedAt({ meta: null }), null);
assert.equal(listUpdatedAt({ meta: { updatedAt: 'not a date' } }), null);
assert.equal(listUpdatedAt({ meta: { updatedAt: '' } }), null);
assert.equal(listUpdatedAt({ meta: 'x' }), null);
assert.equal(listUpdatedAt(null), null);

// ---- Version history values, said for a person ----
assert.equal(formatChangeValue('deadline_at', '2026-09-10'), '10 Sep 2026');
assert.equal(formatChangeValue('deadline_at', '2026-09-10T14:05:00Z'), '10 Sep 2026, 14:05 UTC');
assert.equal(formatChangeValue('deadline_at', '2026-09-17 21:59 UTC'), '17 Sep 2026, 21:59 UTC');
assert.equal(formatChangeValue('deadline_at', '2026-09-10T16:05:00+02:00'), '10 Sep 2026, 14:05 UTC');
assert.equal(formatChangeValue('deadline_at', '9 Oct 2026, 21:59 UTC'), '9 Oct 2026, 21:59 UTC');   // already said: left alone
assert.equal(formatChangeValue('status', 'open'), 'Open');
assert.equal(formatChangeValue('status', 'awarded'), 'Awarded');
assert.equal(formatChangeValue('cpv_codes', "['35200000', '35810000']"), '35200000, 35810000');
assert.equal(formatChangeValue('value_amount', "{'amount': 5000, 'currency': 'EUR'}"), 'EUR 5,000');
assert.equal(formatChangeValue('title_original', null), null);

// ---- Source status: OK is not "recent", and a one-off load is not stale ----
const asOf = new Date('2026-10-12T12:00:00Z');
assert.deepEqual(sourceFreshness({ id: 'ted', status: 'ok', lastRunAt: '2026-10-12T06:00:00Z' }, asOf), { kind: 'ok', note: null });
assert.deepEqual(sourceFreshness({ id: 'ted', status: 'ok', lastRunAt: '2026-10-07T06:00:00Z' }, asOf), { kind: 'stale', note: 'Stale: last ran 5 days ago' });
assert.deepEqual(sourceFreshness({ id: 'pl_atlas', status: 'ok', lastRunAt: '2026-10-01T06:00:00Z' }, asOf), { kind: 'one-off', note: 'One-off load, last run 1 Oct 2026' });
assert.equal(sourceFreshness({ id: 'x', status: 'failed', lastRunAt: '2026-10-01T06:00:00Z' }, asOf).kind, 'failed');
assert.equal(sourceFreshness({ id: 'x', status: 'never', lastRunAt: null }, asOf).kind, 'never');
assert.equal(minimumMet(null), 'Not measured');
assert.equal(minimumMet(1), 'Yes');
assert.equal(minimumMet(0.999), 'No: 99% of the minimum');

// ---- List parameters: an unusable one is said, never silently dropped ----
const said = (sp: Record<string, string>, kind: 'tenders' | 'funding' | 'buyers' = 'tenders') => ignoredFilters(sp, kind);
assert.deepEqual(said({ status: '', from: '', min: '' }), []);
assert.deepEqual(said({ status: 'open', from: '2026-10-01', to: '2026-11-01', min: '10', max: '20', cpv: '35,35120000' }), []);
assert.ok(said({ status: 'bogus' }).some((m) => m.startsWith('Ignored filter: status=bogus')));
assert.ok(said({ from: '2026-13-45' }).some((m) => m.startsWith('Ignored filter: from=2026-13-45')));
assert.ok(said({ to: 'tomorrow' }).some((m) => m.startsWith('Ignored filter: to=tomorrow')));
assert.ok(said({ cpv: 'abc,35' }).some((m) => m.startsWith('Ignored filter: cpv=abc')));
assert.ok(said({ min: 'lots' }).some((m) => m.startsWith('Ignored filter: min=lots')));
assert.ok(said({ max: '-5' }).some((m) => m.startsWith('Ignored filter: max=-5')));
assert.ok(said({ from: '2026-12-01', to: '2026-11-01' }).some((m) => /inverted/.test(m)));
assert.ok(said({ min: '100', max: '5' }).some((m) => /inverted/.test(m)));
assert.ok(said({ status: 'nope' }, 'funding').some((m) => m.includes('status=nope')));
assert.ok(said({ sort: 'nope' }, 'buyers').some((m) => m.includes('sort=nope')));
assert.equal(isDay('2026-02-31'), false);
assert.equal(isDay('2026-02-28'), true);
assert.equal(lastPage(0, 10), 1);
assert.equal(lastPage(95, 10), 10);

// ---- A closed list runs newest deadline first unless a sort was asked for ----
assert.equal(defaultTenderSort('closed'), 'deadline-desc');
assert.equal(defaultTenderSort('open'), 'core-first');   // WP-87: the open list leads with the military goods and works
assert.equal(parseTenderFilters({ status: 'closed' }).sort, 'deadline-desc');
assert.equal(toTenderQuery(parseTenderFilters({ status: 'closed' })), '?status=closed');
assert.equal(toTenderQuery(parseTenderFilters({ status: 'closed', sort: 'deadline-asc' })), '?status=closed&sort=deadline-asc');
assert.equal(toTenderQuery(parseTenderFilters({})), '');

// ---- Languages ----
assert.equal(languageName('SK'), 'Slovak');
assert.equal(languageName('sl'), 'Slovenian');
assert.equal(languageName('Et'), 'Estonian');
assert.equal(languageName('LT'), 'Lithuanian');
assert.equal(languageName('lv'), 'Latvian');
assert.equal(languageName('xx'), 'XX');
for (const c of ['NO', 'IS', 'UK', 'TR', 'RU', 'AR']) assert.notEqual(languageName(c), c, c);
const EU24 = ['bg', 'hr', 'cs', 'da', 'nl', 'en', 'et', 'fi', 'fr', 'de', 'el', 'hu', 'ga', 'it', 'lv', 'lt', 'mt', 'pl', 'pt', 'ro', 'sk', 'sl', 'es', 'sv'];
assert.equal(EU24.length, 24);
for (const c of EU24) assert.ok(LANGUAGES[c], c);

// ---- Call deadlines: a day is a day, a rolling call is open ----
const ref = new Date('2026-10-12T10:00:00Z');
const dated = getCallDeadline({ status: 'open', deadline: '2026-10-13T21:59:00Z', deadlineIsDate: true }, ref);
assert.equal(dated.utc, '13 Oct 2026 (date only)');
assert.ok(!dated.utc.includes('21:59'));
assert.equal(dated.dateOnly, true);
const midnight = getCallDeadline({ status: 'open', deadline: '2026-10-12T00:00:00Z' }, ref);
assert.notEqual(midnight.state, 'closed');                          // a bare date is open to the end of that day
assert.equal(midnight.utc, '12 Oct 2026 (date only)');
const rolling = getCallDeadline({ status: 'open', deadline: '2026-10-05T21:59:00Z', deadlineIsDate: true, rolling: true }, ref);
assert.equal(rolling.rolling, true);
assert.equal(rolling.label, 'Open: rolling submission');
assert.notEqual(rolling.state, 'closed');
assert.equal(getCallDeadline({ status: 'open', deadline: '2026-10-05T21:59:00Z', rolling: false }, ref).state, 'closed');
assert.equal(getCallDeadline({ status: 'open', deadline: '2026-10-05T21:59:00Z' }, ref).state, 'closed');
assert.equal(getCallDeadline({ status: 'closed', deadline: null }, ref).state, 'closed');

// ---- A forthcoming call is "Opens soon" only while its dates allow it ----
assert.equal(callStatusKind('forthcoming', 'normal', '2026-11-01T00:00:00Z', ref), 'upcoming');
assert.equal(callStatusKind('forthcoming', 'normal', null, ref), 'upcoming');
assert.equal(callStatusKind('forthcoming', 'normal', '2026-08-13T00:00:00Z', ref), 'pending');   // opening day passed
assert.equal(callStatusKind('forthcoming', 'closed', '2026-08-13T00:00:00Z', ref), 'closed');    // deadline passed
assert.equal(callStatusKind('open', 'normal', '2026-08-13T00:00:00Z', ref), 'open');

// ---- Placeholder amounts are not values; a call-level budget is shown once ----
assert.equal(isPlaceholderAmount(0), true);
assert.equal(isPlaceholderAmount(0.01), true);
assert.equal(isPlaceholderAmount(1), true);
assert.equal(isPlaceholderAmount(1.5), false);
assert.equal(isPlaceholderAmount(90_000_000), false);
const eur = (amount: number) => ({ amount, currency: 'EUR' });
assert.deepEqual(
  [...repeatedCallBudgets([
    { id: '1', callId: 'A', budget: eur(90), budgetScope: 'call' },
    { id: '2', callId: 'A', budget: eur(90), budgetScope: 'call' },
    { id: '3', callId: 'B', budget: eur(5), budgetScope: 'topic' },
    { id: '4', callId: 'B', budget: eur(5), budgetScope: 'topic' },
    { id: '5', callId: 'A', budget: eur(40), budgetScope: 'call' },
  ])],
  ['2'],
);

// ---- CPV: the code's own title before its group's; the legal basis and the procedure in words ----
assert.deepEqual(cpvName('50640000'), { label: 'Repair and maintenance services of warships', exact: true });
assert.deepEqual(cpvName('79710000'), { label: 'Business services: law, marketing, consulting, recruitment, printing and security', exact: false });
assert.equal(cpvName('99999999'), null);
assert.equal(cpvGroupName('452'), 'Construction work: group 452');
assert.equal(cpvGroupName('351'), 'Emergency and security equipment');
assert.equal(cpvGroupName('999'), null);
assert.equal(legalBasisLabel('32009L0081'), 'Directive 2009/81/EC (defence and security procurement)');
assert.ok(legalBasisLabel('other'));
assert.equal(legalBasisLabel('something-else'), null);
assert.equal(procedureLabel('Negociado con publicidad'), 'Negotiated procedure with prior publication');
assert.equal(procedureLabel('Niet-openbaar'), 'Restricted procedure');
assert.equal(procedureLabel('Procédure négociée'), 'Negotiated procedure');
assert.equal(procedureLabel('Abierto'), 'Open procedure');
assert.equal(procedureLabel('Open procedure'), null);                // already English: shown as stated
assert.equal(procedureLabel('Something unlisted'), null);

// ---- The status the source itself gives ----
assert.equal(sourceStatusWord({ statusNative: 'open' }), null);
assert.equal(sourceStatusWord({ statusNative: 'expired' }), null);
assert.equal(sourceStatusWord({ statusNative: null }), null);
assert.equal(sourceStatusWord({ statusNative: 'awarded' }), 'Awarded');
assert.equal(sourceStatusWord({ statusNative: 'forthcoming' }), 'Planned');

// ---- Calendar ----
assert.deepEqual(resolveMonth(null, '2026-10', '2028-10'), { month: '2026-10', clamped: false });
assert.deepEqual(resolveMonth('2027-03', '2026-10', '2028-10'), { month: '2027-03', clamped: false });
assert.deepEqual(resolveMonth('2031-01', '2026-10', '2028-10'), { month: '2028-10', clamped: true });
assert.deepEqual(resolveMonth('2026-09', '2026-10', '2028-10'), { month: '2026-10', clamped: true });
assert.equal(truncateTitle('Short title'), 'Short title');
assert.equal(Array.from(truncateTitle('x'.repeat(40))).length, 29);
assert.equal(truncateTitle('x'.repeat(40)).endsWith('…'), true);
const all = Array.from({ length: 440 }, (_, i) => i);
assert.equal(pageOf(all, 1, 100).items.length, 100);
assert.deepEqual([pageOf(all, 5, 100).items.length, pageOf(all, 5, 100).pages], [40, 5]);
assert.equal(pageOf(all, 9, 100).page, 5);

// ---- Export: cached ten minutes, 30 entries, 1,000 rows for status=all, six uncached at once ----
assert.equal(exportCap('all', 2000), 1000);
assert.equal(exportCap('open', 2000), 2000);
assert.equal(exportCap('closed', 2000), 2000);
let clock = 0;
const cache = new TtlCache<string>(600_000, 30, () => clock);
for (let i = 0; i < 31; i++) cache.set(`k${i}`, `v${i}`);
assert.equal(cache.size, 30);
assert.equal(cache.get('k0'), undefined);                          // the oldest went first
assert.equal(cache.get('k30'), 'v30');
clock = 599_999;
assert.equal(cache.get('k30'), 'v30');
clock = 600_000;
assert.equal(cache.get('k30'), undefined);                         // ten minutes is the end of it
const gate = new Gate(6);
for (let i = 0; i < 6; i++) assert.equal(gate.enter(), true);
assert.equal(gate.enter(), false);
gate.leave();
assert.equal(gate.enter(), true);

// ---- Market overview: counts of notices, drawn and said ----
assert.equal(monthLabel('2026-10'), 'Oct 2026');
assert.equal(monthLabel('2023-01'), 'Jan 2023');
assert.equal(monthLabel('2026-13'), '2026-13');                    // not a month: left as it came
assert.equal(niceMax(0), 1);
assert.equal(niceMax(-5), 1);
assert.equal(niceMax(7), 10);
assert.equal(niceMax(10), 10);
assert.equal(niceMax(11), 20);
assert.equal(niceMax(230), 500);
assert.equal(niceMax(501), 1000);
assert.equal(percentText(null), 'Not measured');                  // not measured is never 0%
assert.equal(percentText(0), '0%');
assert.equal(percentText(0.0002), 'Under 0.1%');
assert.equal(percentText(0.0074), '0.7%');
assert.equal(percentText(0.123), '12%');
assert.equal(shareOf(1, 0), 0);
assert.equal(shareOf(5, 4), 1);
assert.equal(daysText(null), 'Not measured');
assert.equal(daysText(1), '1 day');
assert.equal(daysText(35), '35 days');
{
  const { max, bars } = barLayout([0, 50, 100, 230], 100, 200, 0);
  assert.equal(max, 500);
  assert.equal(bars.length, 4);
  assert.equal(bars[0].h, 0);                                         // an empty month has no bar, not a sliver
  assert.equal(bars[3].h, 92);                                        // 230 / 500 of the box
  assert.equal(bars[3].y, 200 - 92);
  assert.equal(bars[3].x, 75);                                        // four bars side by side in 100
  const empty = barLayout([], 100, 200);
  assert.equal(empty.bars.length, 0);
  assert.equal(empty.max, 1);
}
assert.equal(heldSpan('2020-11-03', '2026-10-12'), '3 Nov 2020 to 12 Oct 2026');
assert.equal(heldSpan('2026-01-06', '2026-01-06'), '6 Jan 2026');   // one day is one date
assert.equal(heldSpan(null, null), null);                           // a source that dates nothing says so elsewhere
assert.equal(heldSpan(undefined, '2026-10-12'), '12 Oct 2026');
assert.equal(heldSpan('not a date', null), null);
assert.equal(cpvGroupTitle('351'), 'Emergency and security equipment');
assert.equal(cpvGroupTitle('999'), null);                            // a group we do not hold: the code is shown alone
assert.equal(cpvGroupTitle('35'), null);

// ---- Site QA round 2 (14 October 2026): WP-7 ----
// N2: what qualified the notice names the code, or says the buyer did
assert.deepEqual(basisChips({ scope: 'core', legalBasis: '32014L0024', qualifiedBy: ['military_cpv'], militaryCpv: ['35811300'], cpvCodes: ['39162100', '35811300', '30192000'] }),
  ['Military product code (CPV 35811300, among 3 codes)']);
assert.deepEqual(basisChips({ scope: 'core', buyerClass: 'education', qualifiedBy: ['buyer'], militaryCpv: [] }), ['Defence buyer', 'Education body']);
assert.deepEqual(basisChips({ scope: 'core', legalBasis: '32009L0081', qualifiedBy: ['legal_basis', 'military_cpv'], militaryCpv: ['35400000'] }), ['Defence directive (2009/81/EC)']);
assert.equal(militaryCodeChip(['35400000'], ['35400000']), 'Military product code (CPV 35400000)');
assert.equal(militaryCodeChip(['1', '2', '3', '4', '5'], null), 'Military product code (CPV 1, 2, 3 and 2 more)');
// WP-8 (14 October 2026): the two groups that left core are named, never called a defence notice
assert.deepEqual(basisChips({ scope: 'supply', legalBasis: '32009L0081', buyerClass: 'municipal', qualifiedBy: ['directive_civil_buyer'] }),
  ['Filed under the defence procurement directive by a civil buyer', 'Municipal body']);
assert.deepEqual(basisChips({ scope: 'supply', buyerClass: 'security', qualifiedBy: ['security_buyer_cpv'], militaryCpv: ['35321200'] }),
  ['Security-body purchase of a military-type product code', 'Security or interior body']);
assert.ok(scopeGroupNote(['directive_civil_buyer'])?.includes('not a defence or security body'));
assert.equal(scopeGroupNote(['buyer']), null);
assert.ok((TENDER_SCOPES.supply.also ?? '').includes('civil buyer') && (TENDER_SCOPES.supply.also ?? '').includes('Security-body'));
// N13: a notice that closes today does not "close this week"
const noonToday = new Date('2026-10-14T09:00:00Z');
assert.equal(getDeadline('2026-10-14T12:00:00Z', noonToday).label, 'Closes today');
assert.equal(getDeadline('2026-10-16T12:00:00Z', noonToday).label, 'Closes this week');
// N7: a deadline more than three years ahead is a long-running notice
assert.equal(isLongRunning({ anomalies: ['deadline-more-than-3y'] }), true);
assert.equal(isLongRunning({ anomalies: [] }), false);
assert.equal(isLongRunning({}), false);
// N8: a file that holds fewer rows than match says so in its last row; a whole result says nothing
assert.equal(truncationRow(4, 2000, 2000, 2000), null);
const cut = truncationRow(4, 2000, 61521, 2000);
assert.ok(cut && cut.length === 4 && String(cut[0]).startsWith('# Not the whole result') && String(cut[0]).includes('61,521'));
// a cursor export never counts: it says so when the cursor still had rows, and nothing when it did not
assert.equal(truncationRow(4, 1200, null, 2000, false), null);
assert.ok(String(truncationRow(4, 2000, null, 2000, true)?.[0]).includes('and more matched'));
// N6: the holes of a source come from its monthly counts
assert.deepEqual(monthRanges(['2026-05', '2026-06', '2026-07', '2026-12', '2027-01']), ['May to Jul 2026', 'Dec 2026 to Jan 2027']);
assert.deepEqual(monthRanges(['x', '2026-13']), []);
assert.equal(
  gapSentence({ name: 'Poland (e-Zamówienia)', heldFrom: '2026-01-02', heldTo: '2026-10-12', monthlyMedian: 1100, gapMonths: ['2026-02', '2026-03'] }),
  'Poland (e-Zamówienia): publication dates 2 Jan 2026 to 12 Oct 2026. The usual month holds about 1,100 notices. Months with fewer than half of that: Feb to Mar 2026.',
);
assert.equal(gapSentence({ name: 'TED', heldFrom: '2026-01-02', heldTo: '2026-10-12', gapMonths: undefined }), null);
assert.match(gapSentence({ name: 'TED', heldFrom: '2026-01-02', heldTo: '2026-10-12', monthlyMedian: 900, gapMonths: [] }) ?? '', /No whole month/);

async function runnerChecks(): Promise<void> {
  const runner = new ExportRunner<string>(new TtlCache(600_000, 30), new Gate(2));
  const release: (() => void)[] = [];
  const slow = (v: string) => () => new Promise<string>((resolve) => { release.push(() => resolve(v)); });
  const a = runner.get('a', slow('A'));
  const b = runner.get('b', slow('B'));
  const sameAsA = runner.get('a', () => Promise.reject(new Error('must not run twice')));   // shares the running build
  assert.deepEqual(await runner.get('c', slow('C')), { busy: true });                      // the third uncached one is refused
  release.forEach((r) => r());
  assert.deepEqual(await a, { value: 'A' });
  assert.deepEqual(await b, { value: 'B' });
  assert.deepEqual(await sameAsA, { value: 'A' });
  assert.deepEqual(await runner.get('a', () => Promise.reject(new Error('cached'))), { value: 'A' });   // and now it is cached
  await assert.rejects(runner.get('f', () => Promise.reject(new Error('boom'))));
  // A failure is remembered for 30 s (EXPORT_FAILURE_TTL_MS) and not run again meanwhile; export.check.ts checks the expiry.
  await assert.rejects(runner.get('f', async () => 'F'), /boom/);
}

// WP-23 (16 October 2026): the confidence badge says the level and the reason, in words; the CSV cell is the level only
const hi = confidenceView({ level: 'high', basis: ['Military product code', 'Defence buyer'] });
assert.equal(hi?.text, 'Clearly defence');   // WP-88: the level in plain words
assert.equal(hi?.sentence, 'Military product code; Defence buyer.');
assert.equal(hi?.name, 'Clearly defence: Military product code; Defence buyer.');     // the accessible name carries the level and the reason
// WP-95: no probability words; the API's label names the signal, and an older API's level gets a word that does too
assert.equal(confidenceView({ level: 'low', basis: [] })?.name, 'Weak defence signal');       // no reason: the level alone, no empty sentence
assert.equal(confidenceView({ level: 'medium', basis: ['Defence buyer'] })?.text, 'Defence buyer or directive');
assert.equal(confidenceView({ level: 'medium', basis: ['Defence buyer'], label: 'Defence buyer, ordinary purchase' })?.text, 'Defence buyer, ordinary purchase');
assert.equal(confidenceView({ level: 'medium', basis: ['Defence buyer'], label: 'Defence buyer, ordinary purchase' })?.name, 'Defence buyer, ordinary purchase: Defence buyer.');
assert.equal(confidenceView(undefined), null);                                          // an older API build: no badge
assert.equal(confidenceView({ level: 'certain', basis: ['x'] }), null);                 // a level this build does not know is not shown as a wrong word
assert.equal(confidenceCell({ level: 'medium', basis: ['Defence buyer'] }), 'medium');
assert.equal(confidenceCell(null), '');
assert.equal(confidenceCell({ level: '', basis: [] }), '');
assert.ok(CONFIDENCE_HREF.startsWith('/methodology#') && CONFIDENCE_HREF.endsWith('s-how-sure-are-we'));
// the badge never replaces the chips: the same notice gives the same chips with and without a level
assert.deepEqual(basisChips({ scope: 'core', legalBasis: '32009L0081', confidence: { level: 'high', basis: [] } }), ['Defence directive (2009/81/EC)']);

// WP-88: a source by a name a reader knows; other names unchanged
assert.equal(sourceDisplay('PLACSP'), 'Plataforma de Contratación (Spain)');
assert.equal(sourceDisplay('PLACSP (Plataforma de Contratación del Sector Público, Spain)'), 'Plataforma de Contratación del Sector Público, Spain');
assert.equal(sourceDisplay('EU Funding and Tenders Portal (SEDIA)'), 'EU Funding and Tenders Portal');
assert.equal(sourceDisplay('TED'), 'TED');

runnerChecks().then(() => console.log('ui checks passed'), (err) => { console.error(err); process.exit(1); });
