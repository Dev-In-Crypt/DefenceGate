/**
 * Self-check of WP-100 (mobile, feeds, exports; persona round of 23 October 2026, section E). Not part of the app and not imported
 * by it. Run with `npm run check` (scripts/run-checks.mjs), or from web/:
 *   npx tsc lib/wp100.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/wp100.check.js
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { FEED_MAX } from './analyst';
import { buildAtom, feedSubtitle } from './atom';
import { feedLine } from './calendar-counts';
import { MARKET_HEADER, SUPPLIER_CONTRACT_HEADER, csvValueKind, marketRows, supplierContractRows } from './export-tables';
import { listOrder, tooBroad } from './export-cache';
import { feedName, searchSummary } from './feed-name';
import { toCsv } from './csv';
import * as tenderMock from './mock/tenders';
import { supplierContracts } from './mock/suppliers';
import type { MarketStats } from './types';

// ---- 2. A subscription is named after its search ----
assert.equal(feedName('DefenceGate', { q: 'radar', country: ['DE', 'PL'] }), 'DefenceGate: radar, DE+PL');
assert.equal(feedName('DefenceGate deadlines', {}), 'DefenceGate deadlines', 'no search: the plain name');
assert.equal(searchSummary({ country: ['FR', 'ES', 'PT'], cpv: ['3581', '181'], status: 'open' }), 'FR+ES+PT, CPV 3581+181', 'open is the default status');
assert.equal(searchSummary({ scope: 'core', status: 'closed' }), 'military goods and works, closed');
assert.ok(searchSummary({ q: 'x'.repeat(200) }).length <= 80, 'a long search is shortened');
const atomRoute = readFileSync('app/(public)/changes.atom/route.ts', 'utf8');
assert.match(atomRoute, /searchSummary\(filters\)/, 'the feed title reads the search');
assert.match(readFileSync('app/(public)/calendar.ics/route.ts', 'utf8'), /name,\n\s+tendersBeyond/, 'the calendar is named after the search');

// ---- 2. The feed is paged: 400 entries a page, the older ones on its next pages, and it says so ----
assert.equal(FEED_MAX, 400);
assert.match(readFileSync('lib/api.ts', 'utf8'), /FEED_PAGE_ENTRIES = FEED_MAX/, 'the feed holds what the subscribe block says');
assert.match(feedSubtitle(14, 2403, 400, { page: 1, pages: 7, size: 400 }), /holds the newest 400 of the 2,403 changes; the page lists them all\. The older ones are on the next pages of this feed \(400 a page\)\.$/);
assert.match(feedSubtitle(14, 2403, 3, { page: 7, pages: 7, size: 400 }), /Page 7 of 7 of this feed: changes 2,401 to 2,403 of 2,403, newest first\.$/);
assert.ok(!feedSubtitle(14, 300, 300, { page: 1, pages: 1, size: 400 }).includes('holds'), 'a feed that holds the whole window says nothing about pages');
const many = tenderMock.queryChanges({ pageSize: 10 }, new Date('2026-10-12T08:00:00Z')).items;
const paged = buildAtom(many, { origin: 'https://example.test', selfPath: '/changes.atom?page=2', pagePath: '/changes', title: 't', subtitle: 's',
  generatedAt: '2026-10-12T08:00:00Z', first: '/changes.atom', prev: '/changes.atom', next: '/changes.atom?page=3' });
assert.match(paged, /<link rel="next" type="application\/atom\+xml" href="https:\/\/example\.test\/changes\.atom\?page=3"\/>/);
assert.match(paged, /<link rel="previous" type="application\/atom\+xml" href="https:\/\/example\.test\/changes\.atom"\/>/);
assert.ok(!buildAtom(many, { origin: 'https://e.test', selfPath: '/changes.atom', pagePath: '/changes', title: 't', subtitle: 's', generatedAt: '2026-10-12T08:00:00Z' }).includes('rel="next"'));

// ---- 3. The file's default order is the list's: military goods and works first, then the soonest deadline ----
const t = (id: string, deadline: string | null, scope: string, status = 'open') => ({ id, deadline, scope, status, publishedAt: null });
const rows = [t('a', '2026-10-30T00:00:00Z', 'core'), t('b', '2026-10-23T00:00:00Z', 'supply'), t('c', '2026-10-24T00:00:00Z', 'core'), t('d', null, 'core')];
assert.deepEqual(listOrder(rows, 'open', 'core-first').map((x) => x.id), ['c', 'a', 'd', 'b'], 'the default view (p09: 30 October stood first)');
assert.deepEqual(listOrder(rows, 'open', undefined).map((x) => x.id), ['c', 'a', 'd', 'b']);
assert.deepEqual(listOrder(rows, 'open', 'core-first', 'core').map((x) => x.id), ['b', 'c', 'a', 'd'], 'one scope: by deadline alone');
const mixed = [t('x', '2026-10-01T00:00:00Z', 'core', 'closed'), t('y', '2026-11-01T00:00:00Z', 'core'), t('z', '2026-10-25T00:00:00Z', 'supply')];
assert.deepEqual(listOrder(mixed, 'all', 'deadline-asc').map((x) => x.id), ['z', 'y', 'x'], 'All: the open ones first, as the list');
assert.deepEqual(listOrder(mixed, 'closed', 'deadline-desc').map((x) => x.id), ['y', 'z', 'x']);
assert.equal(tooBroad({ status: 'all', scope: 'all', publishedFrom: '2025-01-01' }), false, 'a publication range narrows an export');

// ---- 3. value_kind on every row with a value ----
const tender = (valueKind: string | null, statusNative: string, sourceId: string) => ({ valueKind, statusNative, source: { sourceId } });
assert.equal(csvValueKind(tender('lot_sum', 'open', 'ted')), 'lot sum', 'what the notice states stands');
assert.equal(csvValueKind(tender(null, 'open', 'es_placsp')), 'estimated');
assert.equal(csvValueKind(tender(null, 'awarded', 'es_placsp')), 'estimated', 'a PLACSP value is its estimate or budget, whatever the status');
assert.equal(csvValueKind(tender(null, 'open', 'fr_boamp')), 'estimated');
assert.equal(csvValueKind(tender(null, 'awarded', 'fr_boamp')), 'not stated', 'an award notice of another source: not guessed');
const exportSrc = readFileSync('lib/export.ts', 'utf8');
assert.match(exportSrc, /value \? csvValueKind\(t\) : null/);
assert.match(exportSrc, /listOrder\(read, parsed\.status, parsed\.sort, parsed\.scope\)/);
assert.match(exportSrc, /'x-row-cap-note'/, 'the cap is said in the headers');
assert.match(exportSrc, /link: `<\$\{b\.next\}>; rel="next"`/, 'a cut file names its next part');

// ---- 4. A supplier's contracts: every one, the tender file's attribution columns, no co-winner named ----
for (const col of ['source_name', 'source_url', 'licence', 'attribution', 'page_url']) {
  assert.ok(SUPPLIER_CONTRACT_HEADER.includes(col) && MARKET_HEADER.includes(col === 'source_url' ? 'source_name' : col), col);
}
const demo = supplierContracts('1-demo-airframes-gmbh')!;
const sRows = supplierContractRows(demo, (p) => `https://example.test${p}`);
assert.equal(sRows.length, demo.items.length);
assert.ok(sRows.every((r) => r.length === SUPPLIER_CONTRACT_HEADER.length), 'rectangular');
const col = (name: string) => SUPPLIER_CONTRACT_HEADER.indexOf(name);
for (const r of sRows) {
  assert.equal(r[col('value')] === null, r[col('value_kind')] === null, 'a value has a kind, and no value has none');
  if (r[col('in_contract_sum')] === 'yes') assert.equal(r[col('value_kind')], 'contract', 'only contract values are summed');
  assert.ok(String(r[col('page_url')]).startsWith('https://example.test/tenders/'));
}
const csv = toCsv(SUPPLIER_CONTRACT_HEADER, sRows);
assert.equal(csv.replace(/^﻿/, '').split('\r\n')[0], SUPPLIER_CONTRACT_HEADER.join(','));
assert.ok(supplierContractRows({ ...demo, total: demo.items.length + 1 }, (p) => p).every((r) => r[col('result_truncated')] === 'true'), 'a cut list says so on every row');

// ---- 4. The market tables as shown, with every source's terms ----
const m: MarketStats = {
  asOf: '2026-10-23T08:00:00Z', scope: 'core', unit: 'notices published', windowFrom: '2025-10-24', windowTo: '2026-10-23', sourceCount: 2,
  months: [{ month: '2026-09', count: 10, ted: 7, partial: false }, { month: '2026-10', count: 4, ted: 4, partial: true }],
  countries: { total: 14, items: [{ country: 'PL', count: 12 }], other: 2 },
  sources: [{ id: 'ted', name: 'TED', count: 11 }, { id: 'es_placsp', name: 'PLACSP', count: 3 }],
  amendments: { notices: 0, amended: 0, share: null }, responseWindow: { notices: 0, median: null, p25: null, p75: null },
  cpvGroups: [{ group: '357', count: 9 }], basis: {}, cpv: ['35'],
};
const terms = new Map([['ted', { name: 'TED', licence: 'CC BY 4.0', attribution: '© European Union' }], ['es_placsp', { name: 'PLACSP', licence: 'Ley 37/2007', attribution: 'Ministerio de Hacienda' }]]);
const mRows = marketRows(m, terms, 'https://example.test/market?cpv=35');
const mc = (name: string) => MARKET_HEADER.indexOf(name);
assert.deepEqual(mRows.map((r) => `${r[mc('table')]}:${r[mc('key')]}:${r[mc('notices')]}`),
  ['month:2026-09:10', 'month:2026-10:4', 'country:PL:12', 'country:other:2', 'cpv_group:357:9', 'source:ted:11', 'source:es_placsp:3']);
assert.equal(mRows[0][mc('national_sources')], 3);
assert.equal(mRows[1][mc('partial_month')], 'true');
assert.equal(mRows[2][mc('licence')], 'CC BY 4.0; Ley 37/2007', 'a figure of several sources carries all their terms');
assert.equal(mRows[6][mc('attribution')], 'Ministerio de Hacienda', 'a source row carries its own');
assert.equal(mRows[0][mc('cpv')], '35');
assert.ok(mRows.every((r) => r.length === MARKET_HEADER.length));

// ---- 5. The calendar: one number format, the opening days said beside the deadlines, no "above" ----
assert.equal(feedLine(1503, 5000, 46), 'It holds every one of the 1,503 events these filters give: 1,457 deadlines and 46 opening days and planned deadlines of calls not yet open.');
assert.equal(feedLine(1475), 'It holds every one of the 1,475 events these filters give.');
const cal = readFileSync('app/(public)/calendar/page.tsx', 'utf8');
assert.ok(!cal.includes('deadlines above'), 'the feed box comes before the list on a phone');
assert.match(cal, /\$\{formatNumber\(total\)\} upcoming/);

// ---- 1. Phone layout: deadline and original on the first screen of a tender, open tenders before a buyer's profile ----
const tenderPage = readFileSync('app/(public)/tenders/[slug]/page.tsx', 'utf8');
assert.ok(tenderPage.indexOf('data-phone-first') < tenderPage.indexOf('<LangLabel kind="language"'), 'the deadline block heads the header on a phone');
assert.match(tenderPage, /max-lg:line-clamp-4/);
const buyerPage = readFileSync('app/(public)/buyers/[slug]/page.tsx', 'utf8');
assert.ok(buyerPage.indexOf('id="open-tenders"') < buyerPage.indexOf('<BuyerProfileSection'), 'open tenders before the profile');

console.log('wp100 checks passed');
