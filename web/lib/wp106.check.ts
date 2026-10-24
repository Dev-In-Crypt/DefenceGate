/**
 * WP-106 (persona round of 24 October 2026: tender pages, lists and exports), without a browser:
 * npx tsc lib/wp106.check.ts --outDir /tmp/chk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule
 * && node /tmp/chk/wp106.check.js
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { getDeadline, getTenderDeadline, getCallDeadline, TENDER_SOON_DAYS, urgentLabel } from './deadline';
import { tenderStatusView, winnersLine, subjectAddsTo } from './tender-status';
import { whoMayBid, winnersHref, WHO_MAY_BID_UNKNOWN } from './who-may-bid';
import { csvValueKind, winnerCells } from './export-tables';
import { listOrder } from './export-cache';
import { defaultTenderSort, parseTenderFilters, tenderSortOptions, toTenderQuery } from './filters';
import { buildDigestAtom, digestQuery, parseDigestFilters, restOfTendersHref } from './digest';
import type { Digest } from './types';

// ---- 1. "Closing soon" within 7 days for a tender; the label in days, never "this week" ----
const saturday = new Date('2026-10-24T09:00:00Z');
const tender = (deadline: string) => ({ status: 'open' as const, deadline, statusNative: 'open' });
assert.equal(TENDER_SOON_DAYS, 7);
assert.equal(getTenderDeadline(tender('2026-11-16T12:00:00Z'), saturday).state, 'normal', 'p06: 23 days ahead is not closing soon');
assert.equal(tenderStatusView(tender('2026-11-16T12:00:00Z'), saturday).label, 'Open');
assert.equal(tenderStatusView(tender('2026-10-31T12:00:00Z'), saturday).label, 'Closing soon', '7 days ahead is');
assert.equal(getTenderDeadline(tender('2026-10-28T12:00:00Z'), saturday).label, 'Closes in 4 days', 'p01: Wednesday 28 October, read on Saturday 24');
assert.equal(urgentLabel(0), 'Closes today');
assert.equal(urgentLabel(1), 'Closes tomorrow');
assert.ok(!getDeadline('2026-10-26T12:00:00Z', saturday).label.includes('week'));
// a funding call keeps the 30 days of its list's "Closing soon" status
assert.equal(getCallDeadline({ status: 'open', deadline: '2026-11-16T12:00:00Z' }, saturday).state, 'soon');

// ---- 2. Who may bid: what the legal basis says, with its article; nothing for a basis it does not describe ----
const public24 = whoMayBid('32014L0024')!;
assert.ok(public24.text.includes('Article 18') && public24.text.includes('Article 25') && !public24.defence);
assert.equal(whoMayBid('Ley 9/2017 (LCSP)')!.text, public24.text, 'the Spanish law that transposes 2014/24 reads the same');
const defence = whoMayBid('32009L0081')!;
assert.ok(defence.defence && defence.text.includes('recital 18') && defence.text.includes('Article 21') && defence.text.includes('30 %'));
assert.equal(whoMayBid('Ley 24/2011 (defensa y seguridad)')!.text, defence.text);
assert.ok(whoMayBid('32014L0025')!.text.includes('Article 43'));
assert.equal(whoMayBid('de-uvgo'), null);
assert.equal(whoMayBid(null), null);
assert.ok(WHO_MAY_BID_UNKNOWN.includes('notice'));
for (const r of [public24, defence]) assert.ok(!/advi[cs]e|recommend|should/i.test(r.text), 'no advice beyond the act');
assert.equal(winnersHref('35613000', 'DK'), '/suppliers?cpv=35613&buyerCountry=DK', 'p08: drone winners under the notice code, in its country');
assert.equal(winnersHref('35000000', null), '/suppliers?cpv=35');
assert.equal(winnersHref(null, 'DK'), null);

// ---- 3. The award in a list: winners and value kind; the subject only when it adds to the title ----
assert.equal(winnersLine({ awardedTo: [{ name: 'A', slug: null, country: 'ES' }, { name: 'B', slug: null, country: 'ES' }, { name: 'C', slug: null, country: 'PT' }], awardedPersons: 1 }),
  'A; B and 1 more; and a natural person, not named');
assert.equal(winnersLine({ awardedTo: [], awardedPersons: 0 }), null);
assert.equal(subjectAddsTo('GELENKWELLE MIT AUSGLEICHSGELENK, FAHRZE', '6003114831-BAAINBw E2.3Y E23Y003299'), 'GELENKWELLE MIT AUSGLEICHSGELENK, FAHRZE');
assert.equal(subjectAddsTo('Road transport services', 'Netherlands – Road transport services'), null, 'not the title again');

// ---- 4. The CSV: one value-kind vocabulary with the supplier file, and the winners ----
const row = (valueKind: string | null, statusNative: string, awardValue: { amount: number; currency: string; kind: 'contract' | 'framework' | 'estimate' } | null = null) =>
  ({ valueKind, statusNative, awardValue, source: { sourceId: 'ted' } });
assert.equal(csvValueKind(row('total', 'awarded', { amount: 4830000, currency: 'EUR', kind: 'framework' })), 'framework ceiling');
assert.equal(csvValueKind(row('total', 'awarded', { amount: 1, currency: 'EUR', kind: 'contract' })), 'contract');
assert.equal(csvValueKind(row('estimated', 'open')), 'estimate');
assert.equal(csvValueKind(row('total', 'open')), 'estimate', "TED's total on a call is its estimate");
assert.equal(csvValueKind(row('total', 'awarded')), 'not stated', 'an award total not classified: not guessed');
assert.equal(csvValueKind(row('first_lot', 'open')), 'estimate (first lot)');
const supplierKinds = ['contract', 'framework ceiling', 'estimate'];
for (const k of ['contract', 'framework', 'estimate'] as const) assert.ok(supplierKinds.includes(csvValueKind(row(null, 'awarded', { amount: 5, currency: 'EUR', kind: k }))));
assert.deepEqual(winnerCells({ awardedTo: [{ name: 'Scan Global Logistics', slug: null, country: 'DK' }, { name: 'Seko', slug: null, country: null }] }),
  ['Scan Global Logistics | Seko', 'DK | ']);
const exportSrc = readFileSync('lib/export.ts', 'utf8');
assert.match(exportSrc, /'confidence',\n {2}\/\/ WP-106[^\n]*\n {2}'winners', 'winner_countries',\n\];/, 'the winner columns come last: the order of the others never moves');

// ---- 5. Sorts: by value per currency, by code, and All with the rest newest first ----
assert.equal(defaultTenderSort('all'), 'open-first');
assert.equal(toTenderQuery(parseTenderFilters({ status: 'all' })), '?status=all', 'the default of All is not written into the address');
assert.equal(toTenderQuery(parseTenderFilters({ status: 'all', sort: 'value-desc' })), '?status=all&sort=value-desc');
assert.deepEqual(tenderSortOptions('open').map((o) => o.value), ['core-first', 'deadline-asc', 'deadline-desc', 'published-desc', 'value-desc', 'cpv-asc']);
assert.deepEqual(tenderSortOptions('all').map((o) => o.value)[0], 'open-first');
assert.ok(!tenderSortOptions('closed').some((o) => o.value === 'core-first' || o.value === 'open-first'));
type R = { id: string; deadline: string | null; status: string; estimatedValue: { amount: number; currency: string } | null; cpv: string | null };
const r = (id: string, deadline: string | null, status: string, value: [number, string] | null, cpv: string | null): R =>
  ({ id, deadline, status, estimatedValue: value ? { amount: value[0], currency: value[1] } : null, cpv });
const items = [r('old', '2017-03-01T00:00:00Z', 'closed', [10, 'EUR'], '35420000'), r('open', '2026-11-20T00:00:00Z', 'open', null, '18000000'),
  r('recent', '2026-10-10T00:00:00Z', 'closed', [9000, 'PLN'], '34330000'), r('big', '2026-09-01T00:00:00Z', 'closed', [500, 'EUR'], null),
  r('placeholder', '2026-09-02T00:00:00Z', 'closed', [1, 'EUR'], '30000000')];
assert.deepEqual(listOrder(items, 'all', 'open-first').map((x) => x.id), ['open', 'recent', 'placeholder', 'big', 'old'], 'p04/p07: no 2017 under the open ones');
assert.deepEqual(listOrder(items, 'all', undefined).map((x) => x.id), ['open', 'recent', 'placeholder', 'big', 'old']);
assert.deepEqual(listOrder(items, 'all', 'deadline-asc').map((x) => x.id), ['open', 'old', 'big', 'placeholder', 'recent'], 'oldest first when asked for');
assert.deepEqual(listOrder(items, 'all', 'value-desc').map((x) => x.id).slice(0, 3), ['big', 'old', 'recent'], 'EUR largest first, then PLN apart');
assert.deepEqual(listOrder(items, 'all', 'cpv-asc').map((x) => x.id), ['open', 'placeholder', 'recent', 'old', 'big']);

// ---- 6. The digest by CPV code: the filter travels with the address, the feed and the change list ----
const f = parseDigestFilters({ country: 'pl', cpv: '353,2461, 35000000-1, x' });
assert.deepEqual(f, { country: 'PL', cpv: ['353', '2461', '35000000'] });
assert.equal(digestQuery(f), '?country=PL&cpv=353%2C2461%2C35000000');
assert.equal(restOfTendersHref('2026-W42', 'new', 'PL', ['353']), '/changes?week=2026-W42&kind=new&country=PL&cpv=353');
const issue = { week: '2026-W42', weekFrom: '2026-10-12T00:00:00Z', weekTo: '2026-10-19T00:00:00Z', counts: { tendersNew: 0, tendersAmended: 0, callsNew: 0, callsAmended: 0, callsOpened: 0, callsClosing: 0, cascade: 0 },
  callsNew: [], callsOpened: [], callsAmended: [], callsClosing: [], tendersNew: [], tendersAmended: [] } as unknown as Digest;
const atom = buildDigestAtom([issue], { origin: 'https://e.test', country: 'PL', cpv: ['353'], generatedAt: '2026-10-24T00:00:00Z' });
assert.ok(atom.includes('/digest.atom?country=PL&amp;cpv=353') && atom.includes('(PL, CPV 353)') && atom.includes(':cpv-353'), 'a narrowed feed is its own feed');

// ---- 7. The pages read these (source checks) ----
const page = readFileSync('app/(public)/tenders/[slug]/page.tsx', 'utf8');
assert.match(page, /data-who-may-bid/);
assert.match(page, /data-who-wins/);
assert.match(page, /data-stages/);
const card = readFileSync('components/dg/cards.tsx', 'utf8');
assert.match(card, /AWARD_VALUE_LABEL\[award\.kind\]/);
assert.match(card, /tender\.cpvTitles\?\.\[tender\.cpv\]/);
const css = readFileSync('app/globals.css', 'utf8');
assert.match(css, /main form, main button, main select, nav, \[role="search"\], \[data-print-hide\], \[data-apply-summary\] \{ display: none !important; \}/);
for (const f2 of ['components/dg/download-link.tsx', 'app/(public)/market/page.tsx', 'app/(public)/suppliers/[slug]/page.tsx']) {
  assert.ok(!/\.csv[^\n]*\} download /.test(readFileSync(f2, 'utf8')), `${f2}: a CSV link has no download attribute, so a 429 is shown and not saved as the file`);
}

console.log('wp106 checks passed');
