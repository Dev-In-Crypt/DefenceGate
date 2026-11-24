/**
 * WP-174 (full QA of 24 November 2026, tenders and feeds): the web side. Not part of the app and not imported by it.
 * Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CPV_PRESETS } from './analyst';
import { buildAtom, entryTitle, feedHeaders } from './atom';
import { spanText } from './contract-period';
import { countsSentence } from './digest';
import { listOrder } from './export-cache';
import { defaultTenderSort, parseTenderFilters, tenderSortOptions, toTenderQuery } from './filters';
import { callHeading, isReferenceOnly, noticeHeading } from './headings';
import { searchStatusLine } from './tender-status';
import type { Call, Change, ContractPeriod, FundingChange, Tender } from './types';

// ---- B-7: a list of one group has nothing to put first; Everything leads with the military goods and works, as the API does
assert.equal(defaultTenderSort('open', 'supply'), 'deadline-asc');
assert.equal(defaultTenderSort('open', 'core'), 'deadline-asc');
assert.equal(defaultTenderSort('open', 'all'), 'core-first');
assert.equal(defaultTenderSort('open'), 'core-first');
assert.ok(!tenderSortOptions('open', 'supply').some((o) => o.value === 'core-first'));
assert.equal(tenderSortOptions('open', 'all')[0].value, 'core-first');
const supply = parseTenderFilters({ scope: 'supply' });
assert.equal(supply.sort, 'deadline-asc');
assert.equal(toTenderQuery(supply), '?scope=supply', 'the default order of the scope is not written into the address');
assert.equal(toTenderQuery(parseTenderFilters({ scope: 'supply', sort: 'core-first' })), '?scope=supply&sort=core-first');
// F30: the label fits a phone's sort box
assert.ok(tenderSortOptions('open')[0].label.length <= 32);

// ---- B-3: the Closed export, newest deadline first, puts a notice closed before its stated deadline last
const ref = Date.parse('2026-11-24T10:00:00Z');
const row = (id: string, deadline: string) => ({ id, deadline, status: 'closed' });
assert.deepEqual(listOrder([row('ahead', '2027-07-31T11:00:00Z'), row('old', '2026-01-01T00:00:00Z'), row('recent', '2026-11-20T00:00:00Z')],
  'closed', undefined, 'relevant', ref).map((r) => r.id), ['recent', 'old', 'ahead']);
assert.deepEqual(listOrder([row('ahead', '2027-07-31T11:00:00Z'), row('old', '2026-01-01T00:00:00Z')], 'closed', 'deadline-asc', 'relevant', ref)
  .map((r) => r.id), ['old', 'ahead'], 'asked for the other way, the deadline order');
// B-7 in the export: Everything leads with the core notices
assert.deepEqual(listOrder([{ id: 's', deadline: '2026-12-01T00:00:00Z', scope: 'supply' }, { id: 'c', deadline: '2026-12-20T00:00:00Z', scope: 'core' }],
  'open', undefined, 'all', ref).map((r) => r.id), ['c', 's']);

// ---- A-3, B-18: headings a reader can use
assert.ok(isReferenceOnly('DAF_2026_000182') && isReferenceOnly('2026/AR44U/00005142E'));
assert.ok(!isReferenceOnly('Short proposal') && !isReferenceOnly('Radar') && !isReferenceOnly(''));
assert.equal(noticeHeading({ title: 'DAF_2026_000182', cpvCodes: ['35400000'] }), 'Military vehicles and associated parts (DAF_2026_000182)');
assert.equal(noticeHeading({ title: 'DAF_2026_000182', cpvCodes: ['35400000'], cpvTitles: { '35400000': 'Own title' } }), 'Own title (DAF_2026_000182)');
assert.equal(noticeHeading({ title: 'FOURNITURE DE PIECES DE RECHANGE', cpvCodes: [] }), 'Fourniture de pieces de rechange');
assert.equal(noticeHeading({ title: 'Armoured vehicles', cpvCodes: ['35400000'] }), 'Armoured vehicles');
assert.equal(callHeading({ title: 'Short proposal', programme: 'HORIZON', programmeName: 'EIC Accelerator' }), 'EIC Accelerator: Short proposal');
assert.equal(callHeading({ title: 'Maturing projects', programme: 'HORIZON', programmeName: 'Horizon Europe' }), 'Maturing projects');

// ---- A-2: one list, newest first, calls and notices together; F24: a stylesheet for a browser
const tender = (over: Partial<Tender>): Tender => ({
  id: '7', slug: '7-x', noticeId: 'N-7', title: 'DAF_2026_000182', titleLanguage: 'fr', originalTitle: null, originalLanguage: null,
  buyerId: '3', buyerSlug: '3-m', buyerName: 'Ministère des Armées', country: 'FR', cpv: '35400000', cpvCodes: ['35400000'], procedure: null,
  legalBasis: null, scope: 'core', deadline: null, publishedAt: null, estimatedValue: null, status: 'open', statusNative: 'open', amended: false,
  versionCount: 1, securityClearance: false, subcontracting: false, sameNotice: [],
  source: { sourceId: 'ted', sourceName: 'TED', url: null, retrievedAt: '2026-11-20T06:00:00Z', licence: '', attribution: '' },
  ...over,
} as Tender);
const changes: Change[] = [
  { id: 'n-new', kind: 'new', day: '2026-11-23', detectedAt: '2026-11-23T08:00:00Z', changes: [], tender: tender({}) },
  { id: 'n-old', kind: 'new', day: '2026-11-20', detectedAt: '2026-11-20T08:00:00Z', changes: [], tender: tender({ id: '8', slug: '8-y', title: 'Boots' }) },
];
const call = { id: '25', slug: '25-eic', programme: 'HORIZON', programmeName: 'EIC Accelerator', funder: 'European Commission', title: 'Short proposal',
  titleLanguage: 'en' } as unknown as Call;
const funding: FundingChange[] = [{ id: 'call-25', kind: 'call-new', day: '2026-11-21', detectedAt: '2026-11-21T08:00:00Z', changes: [], call }];
const atom = buildAtom(changes, { origin: 'https://x.test', selfPath: '/changes.atom', pagePath: '/changes', title: 't', subtitle: 's',
  generatedAt: '2026-11-24T00:00:00Z' }, funding);
const order = [...atom.matchAll(/<id>tag:x\.test,2026:change:([^<]+)<\/id>/g)].map((m) => m[1]);
assert.deepEqual(order, ['n-new', 'call-25', 'n-old']);
assert.ok(atom.includes('New funding call: EIC Accelerator: Short proposal'));
assert.equal(entryTitle(changes[0]), 'New: Military vehicles and associated parts (DAF_2026_000182)');
assert.ok(atom.split('\n')[1] === '<?xml-stylesheet type="text/css" href="/feed.css"?>');
for (const f of ['lib/digest.ts', 'lib/funding-feed.ts', 'lib/regulation.ts']) assert.ok(readFileSync(f, 'utf8').includes('href="/feed.css"'), f);
assert.ok(readFileSync('public/feed.css', 'utf8').includes('feed::before'));
// a browser gets XML (drawn with the stylesheet), a reader the Atom type
assert.equal(feedHeaders(new Request('https://x.test/changes.atom', { headers: { accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' } }))['content-type'], 'application/xml; charset=utf-8');
assert.equal(feedHeaders(new Request('https://x.test/changes.atom', { headers: { accept: 'application/atom+xml, */*' } }))['content-type'], 'application/atom+xml; charset=utf-8');
assert.equal(feedHeaders(new Request('https://x.test/changes.atom'))['vary'], 'accept');
for (const f of ['changes', 'digest', 'funding', 'regulation']) assert.ok(readFileSync(`app/(public)/${f}.atom/route.ts`, 'utf8').includes('...feedHeaders(request)'), f);

// ---- B-11: a period with one end says which
const none: ContractPeriod = { start: null, end: null, endBasis: null, estimatedFrom: null, duration: null, durationUnit: null, renewal: null, renewalsMax: null };
assert.equal(spanText({ ...none, end: '2026-11-25' }), 'Ends 25 Nov 2026, start not stated');
assert.equal(spanText({ ...none, start: '2026-11-01' }), 'Starts 1 Nov 2026, end not stated');
assert.equal(spanText({ ...none, start: '2026-01-01', end: '2026-12-31' }), '1 Jan 2026 – 31 Dec 2026');

// ---- B-15, B-16, B-17: wording
assert.equal(searchStatusLine({ status: 'open', deadline: '2026-11-26T11:00:00Z', statusNative: 'open' }, new Date(ref)), 'Deadline 26 Nov 2026, 11:00 UTC');
assert.ok(countsSentence({ counts: { callsNew: 0, callsOpened: 0, callsClosing: 0, tendersNew: 964, tendersAmended: 3, cascade: 0 } } as never)
  .includes('964 new defence notices (calls and awards)'));
const digestView = readFileSync('components/digest/digest-view.tsx', 'utf8');
assert.ok(!digestView.includes('</time> UTC'), 'no "29 Jan 2027 UTC": a day is not in a time zone');
assert.ok(digestView.includes("'see it' : 'see them'"));
const search = readFileSync('app/(public)/search/page.tsx', 'utf8');
assert.ok(search.includes('Open it in the list of') && !search.includes("'the' : 'all'"), 'no "See the 1 company"');

// ---- F08: the radar chip holds the radar spare parts
const radar = CPV_PRESETS.find((p) => p.id === 'radar-sonar');
assert.ok(radar && (radar.codes as readonly string[]).includes('32352200'));

// ---- F29, B-19: a list of one; the subscribe panel names what follows the filters
assert.ok(readFileSync('components/dg/list-page.tsx', 'utf8').includes('`1 ${nounOne}`'));
assert.ok(readFileSync('app/(public)/tenders/(list)/page.tsx', 'utf8').includes('nounOne="tender"'));
assert.ok(readFileSync('components/tenders/subscribe.tsx', 'utf8').includes('The calendar and the feed below follow every filter'));

console.log('wp174.check: ok');
