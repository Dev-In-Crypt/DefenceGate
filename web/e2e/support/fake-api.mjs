// A fake of the parts of the API that WP-52b reads, shaped as docs/design/API_CONTRACT.md ("Changes of 19 October 2026") says, with the
// numbers of the UX audit of 19 October 2026: 1,449 open notices with a deadline (593 in November), 287,634 closed notices that stop at
// position 10,000, 2,311 changes in 14 days (3,100 for Poland), a digest week of 873 new notices. For e2e/wp52b-api.spec.ts, e2e/wp127-api.spec.ts and
// e2e/wp132-api.spec.ts (five funding calls, 9001-9005), e2e/wp145-api.spec.ts (9005, 9006) and e2e/wp152-api.spec.ts (the company report).
//
// `npx playwright test` against a local build starts it and a second `next start` that reads it (playwright.config.ts, the
// fake-api-* projects, WP-128). By hand, against a site of your own:
//   node e2e/support/fake-api.mjs [port]              then:  DG_API_URL=http://127.0.0.1:4010 npx next start -p 3100
//   E2E_FAKE_API=1 E2E_BASE_URL=http://127.0.0.1:3100 npx playwright test e2e/wp52b-api.spec.ts
//
// Every path it does not know answers 404 (the site treats that as "no such record"). Dates are relative to the pinned site clock
// (NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z, the CI build): the calendar's deadlines are from 20 October on.
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';

const PORT = Number(process.argv[2] ?? process.env.FAKE_API_PORT ?? 4010);
const NOW = '2026-10-12T08:00:00Z';
const SRC = { sourceId: 'ted', sourceName: 'TED', url: 'https://ted.europa.eu/en/notice/-/detail/1', retrievedAt: '2026-10-11T06:20:00Z', lastChangeKind: 'first_seen', licence: 'Commission Decision 2011/833/EU', attribution: '© European Union, TED' };
const stats = { requests: [] };
const busyOnce = new Set();

const tender = (n, over = {}) => ({
  id: String(n), slug: `${n}-notice-${n}`, noticeId: `${n}-2026`, title: `Notice ${n}`, titleLanguage: 'en', originalTitle: null, originalLanguage: null,
  buyerId: '5', buyerSlug: '5-fake-buyer', buyerName: 'Fake Defence Buyer', country: 'DE', cpv: '35800000', cpvCodes: ['35800000'], procedure: 'Open procedure',
  legalBasis: '32009L0081', scope: 'core', deadline: '2026-11-20T10:00:00Z', publishedAt: '2026-10-01T00:00:00Z', estimatedValue: null, status: 'open', statusNative: 'open',
  amended: false, versionCount: 1, securityClearance: false, subcontracting: false, sameNotice: [], source: SRC, ...over,
});
const closed = (n) => tender(n, { title: `Closed notice ${n}`, deadline: '2025-03-01T10:00:00Z', status: 'closed', statusNative: 'expired' });

// ---- The calendar: 450 in October (from the 20th), 593 in November, 406 in December ----
function calendar() {
  const items = [];
  const add = (count, month, first, span, base) => {
    for (let i = 0; i < count; i += 1) {
      const day = first + (i % span);
      items.push({
        id: String(base + i), slug: `${base + i}-calendar-notice-${base + i}`, noticeId: `${base + i}-2026`, title: `Calendar notice ${base + i}`,
        buyerName: 'Fake Defence Buyer', country: ['DE', 'PL', 'FR'][i % 3], deadline: `2026-${month}-${String(day).padStart(2, '0')}T${String(8 + (i % 9)).padStart(2, '0')}:00:00Z`,
        deadlineFrom: null, scope: 'core', status: 'open', statusNative: 'open', anomalies: [], sourceName: 'TED',
      });
    }
  };
  add(450, '10', 20, 12, 10_000);
  add(593, '11', 1, 30, 20_000);
  add(406, '12', 1, 28, 30_000);
  return { items, total: items.length, truncated: false, asOf: NOW };
}

// ---- The changes: `total` of the window, 100 new for every 14 amended, country PL has 3,100 ----
function changes(q) {
  const week = q.get('week');
  const kind = q.get('kind');
  const country = q.get('country');
  const all = week ? { new: 873, amended: 79 } : { new: country === 'PL' ? 2900 : 2100, amended: country === 'PL' ? 200 : 211 };
  const total = kind ? all[kind] : all.new + all.amended;
  const size = Number(q.get('pageSize') ?? 50);
  const page = Number(q.get('page') ?? 1);
  const items = [];
  for (let i = (page - 1) * size; i < Math.min(total, page * size); i += 1) {
    const isNew = kind ? kind === 'new' : i < all.new;
    const n = 100_000 + i;
    items.push({
      id: `${n}-20261010`, kind: isNew ? 'new' : 'amended', day: '2026-10-10', detectedAt: `2026-10-10T${String(6 + (i % 12)).padStart(2, '0')}:${String(i % 60).padStart(2, '0')}:00Z`,
      changes: isNew ? [] : [{ field: 'deadline_at', label: 'Deadline', before: '1 Nov 2026', after: '8 Nov 2026' }], tender: tender(n),
    });
  }
  return {
    items, total, page, pageSize: size, windowDays: week ? 7 : 14, windowFrom: week ? '2026-10-12T00:00:00Z' : '2026-09-28T08:00:00Z', windowTo: week ? '2026-10-19T00:00:00Z' : NOW,
    counts: all, funding: [], fundingTotal: 0, meta: { updatedAt: NOW },
  };
}

// ---- The digest of week 42: 30 rows that stand for 49 notices, one of them 13 times ----
function digest(week) {
  const row = (n, repeats) => ({ id: String(200_000 + n), slug: `${200_000 + n}-digest-notice-${n}`, kind: 'new', day: '2026-10-18', title: `Dzierżawa stacji transformatorowej ${n}`, buyerName: 'Rejonowy Zarząd Infrastruktury Olsztyn', country: 'PL', deadline: null, estimatedValue: null, changes: [], ...(repeats ? { repeats } : {}) });
  const rows = [row(0, 13), row(1, 5), row(2, 2), row(3, 2), row(4, 2), ...Array.from({ length: 25 }, (_, i) => row(5 + i))];
  return {
    week, weekFrom: '2026-10-12T00:00:00Z', weekTo: '2026-10-19T00:00:00Z', closingUntil: '2026-11-02T00:00:00Z', generatedAt: '2026-10-19T04:00:00Z', sectionLimit: 30,
    counts: { tendersNew: 873, tendersAmended: 79, callsNew: 0, callsAmended: 0, callsOpened: 0, callsClosing: 0, cascade: 0 },
    tendersNew: rows, tendersAmended: [], callsNew: [], callsAmended: [], callsOpened: [], callsClosing: [], cascadeCalls: [], cascadeOpenNow: 0,
    country: null, previousWeek: '2026-W41', nextWeek: null, meta: { updatedAt: NOW },
  };
}

const sources = () => ({
  generatedAt: NOW,
  sources: [
    { id: 'ted', name: 'TED', country: 'EU', type: 'tenders', url: 'https://ted.europa.eu', lastRunAt: '2026-10-12T06:00:00Z', status: 'ok', records: 400, coverage: 1, licence: 'CC', attribution: 'TED', updateFreq: 'daily', staleAfterHours: 72, stale: false },
    { id: 'cordis', name: 'CORDIS', country: 'EU', type: 'grants', url: 'https://cordis.europa.eu', lastRunAt: '2026-10-07T19:10:00Z', status: 'ok', records: 900, coverage: 1, licence: 'CC', attribution: 'CORDIS', updateFreq: 'monthly', staleAfterHours: 960, stale: false },
    { id: 'edf', name: 'European Defence Fund: project factsheets', country: 'EU', type: 'grants', url: 'https://example.test', lastRunAt: '2026-10-07T19:10:00Z', status: 'partial', records: 284, coverage: 1, licence: 'CC', attribution: 'EDF', updateFreq: 'monthly', staleAfterHours: 960, stale: false, statusReason: '1 factsheets could not be read; the rest of the run is kept.', statusReasonKind: 'unreadable' },
    { id: 'placsp', name: 'Plataforma de Contratación del Sector Público', country: 'ES', type: 'tenders', url: 'https://example.test', lastRunAt: '2026-10-12T06:00:00Z', status: 'partial', records: 19648, coverage: 1, licence: 'CC', attribution: 'PLACSP', updateFreq: 'daily', staleAfterHours: 72, stale: false, statusReason: "The source's live feed had published nothing new for longer than expected when the run ended.", statusReasonKind: 'stale_feed' },
    { id: 'late', name: 'A daily source that missed its runs', country: 'FR', type: 'tenders', url: 'https://example.test', lastRunAt: '2026-10-07T06:00:00Z', status: 'ok', records: 10, coverage: 1, licence: 'CC', attribution: 'Late', updateFreq: 'daily', staleAfterHours: 72, stale: true },
  ],
});

// ---- WP-144 item 5 (e2e/wp144-api.spec.ts): a buyer whose only defence notice is outside the default scope (production's 9421,
// "Dyrektor Urzędu Morskiego w Gdyni", TED 122655-2017: a military code bought by a maritime office, dual-use) ----
const OUTSIDE_BUYER = {
  id: '779003', slug: '779003-dyrektor-urzedu-morskiego-w-gdyni', name: 'Dyrektor Urzędu Morskiego w Gdyni', country: 'PL', tenderCount: 1,
  openCount: 0, openCoreCount: null, lastPublishedAt: '2017-03-30T00:00:00Z', isDefenceBuyer: false, nameVariants: 0, organisationSlug: null,
  scope: 'all', cpvCount: null, variantNames: [], units: [],
};
const outsideNotice = () => tender(779004, {
  title: 'Command and control system for the maritime office', noticeId: '122655-2017', buyerId: '779003', buyerSlug: OUTSIDE_BUYER.slug,
  buyerName: OUTSIDE_BUYER.name, country: 'PL', scope: 'supply', dualUse: true, buyerClass: 'other', legalBasis: null,
  deadline: '2017-05-10T10:00:00Z', publishedAt: '2017-03-30T00:00:00Z', status: 'closed', statusNative: 'expired',
});

function tenders(q) {
  const status = q.get('status') ?? 'open';
  if (q.get('buyer') === '779003') {
    // the notice is listed under All notices only, as the API's scope filter reads it
    const items = q.get('scope') === 'all' && (status === 'closed' || status === 'all') ? [outsideNotice()] : [];
    return [200, { items, total: items.length, totalCapped: false, page: 1, pageSize: Number(q.get('pageSize') ?? 10), maxOffset: 10_000, meta: { updatedAt: NOW }, asOf: NOW }];
  }
  const size = Number(q.get('pageSize') ?? 10);
  const page = Number(q.get('page') ?? 1);
  const offset = (page - 1) * size;
  if (offset >= 10_000) return [503, { detail: 'the query took too long; narrow the request' }];
  // A list the data service cannot answer (WP-63): the site's error state, with no last good answer to fall back on.
  if (q.get('q') === 'unavailable') return [503, { detail: 'the query took too long; narrow the request' }];
  const search = (q.get('q') ?? '') !== '';
  let total = 1522;
  let capped = false;
  if (status === 'closed' || status === 'all') { total = search ? 10_000 : 287_634; capped = search; }
  if (status === 'planned') total = 6280;
  const items = [];
  for (let i = offset; i < Math.min(total, offset + size); i += 1) items.push(status === 'closed' ? closed(300_000 + i) : tender(300_000 + i));
  return [200, { items, total, totalCapped: capped, page, pageSize: size, maxOffset: 10_000, meta: { updatedAt: NOW }, asOf: '2026-10-12T07:55:00Z' }];
}

// ---- WP-132: funding calls as production served them on 25 October 2026 (e2e/wp132-api.spec.ts): one outside the scope rule, one the
// portal stopped listing, one closing today on a date only, one closing today at 17:00 Brussels, one EDIP call filed under the EDF ----
const EU_SRC = { sourceId: 'eu_portal', sourceName: 'EU Funding & Tenders Portal', url: 'https://ec.europa.eu/info/funding-tenders/opportunities/portal/x', retrievedAt: '2026-10-12T04:20:00Z', licence: 'CC BY 4.0', attribution: '© European Union' };
const fundingCall = (id, over = {}) => ({
  id: String(id), slug: `${id}-wp132-call-${id}`, programme: 'HORIZON', programmeName: 'Horizon Europe', funder: 'European Commission', callId: 'HORIZON-CL3-2026-01',
  topicId: `HORIZON-CL3-2026-01-WP132-${id}`, title: `WP-132 call ${id}`, titleLanguage: 'en', originalTitle: null, originalLanguage: null, regime: 'defence',
  funderCountry: 'EU', issuer: null, status: 'open', sourceStatus: 'open', openingDate: '2025-11-06T00:00:00Z', deadline: '2026-11-05T22:59:59Z', deadlineIsDate: true,
  rolling: false, anomalies: [], budget: { amount: 6000000, currency: 'EUR' }, budgetScope: 'topic', budgetNote: null, actionType: 'Research and Innovation Action',
  fundingRate: null, scope: [], eligibility: [], cascade: null, openToUkraine: null, whoMayApply: 'companies', researchMayApply: true, smeOnly: null,
  publishedAt: '2025-11-06T00:00:00Z', firstSeenAt: '2026-09-24T09:42:00Z', lastSeenAt: '2026-10-12T04:20:00Z', source: EU_SRC,
  conditionsText: null, fundsSummary: null, whoCanApply: [], documents: [], documentEligibility: null, eligibilityState: 'no_source', eligibilitySources: [],
  cascadeBasis: null, partnerArea: null, ukraineBasis: null, rulesApply: null, outOfScope: false, ...over,
});
const FUNDING = {
  9001: fundingCall(9001, { regime: 'dual-use', title: 'RAISE doctoral networks for AI in science', deadline: '2026-10-20T21:59:59Z', outOfScope: true }),
  9002: fundingCall(9002, { status: 'unlisted', sourceStatus: 'forthcoming', title: 'European network for upscaling venture builders', deadline: '2027-02-02T22:59:59Z', lastSeenAt: '2026-10-07T04:20:17Z' }),
  9003: fundingCall(9003, { title: 'Advanced materials for miniaturised energy harvesting', deadline: '2026-10-12T21:59:59Z' }),
  9004: fundingCall(9004, { title: 'Strengthening cybersecurity capacities', programme: 'DIGITAL', programmeName: 'Digital Europe Programme', deadline: '2026-10-12T15:00:00Z', deadlineIsDate: false }),
  9005: fundingCall(9005, { title: 'Key electronic components', programme: 'EDIP', programmeName: 'European Defence Fund', topicId: 'EDF-EDIP-P-2027-LS-IRA-KEC' }),
  // WP-145 (e2e/wp145-api.spec.ts): an EDIP call whose document says Ukrainian entities cannot receive funding. No production call
  // document says so (26 October 2026): the sentence is made up for the test.
  9006: fundingCall(9006, { title: 'Precision engagement', programme: 'EDIP', programmeName: 'European Defence Fund', topicId: 'EDF-EDIP-P-2027-LS-IRA-PE',
    ukraineNoFunding: true, ukraineBasis: { reason: 'call_document_no_funding', evidence: 'Entities established in Ukraine are not eligible to receive funding under this call.' } }),
};

// ---- WP-152 (e2e/wp152-api.spec.ts): a company whose report is open (DGATE_COMPANY_REPORT_OPEN=1), and two accounts: session "a" x 43
// may open it (`company_report` among its features), session "b" x 43 may not. Invented names and numbers.
const REPORT_SLUG = '152001-fake-defence-gmbh';
// WP-155 (e2e/wp155-api.spec.ts): the owner's plan split, with the plans on sale (`/v1/account/status` plansOnSale). Session "a" x 43 is
// Pro (reports 1 of 3 this month, the full competitor list and signals, no CSV), "b" x 43 has no plan, "c" x 43 is Consultant (its name on
// reports, the signals CSV, the gap analysis), "d" x 43 is Pro with this month's reports used. 155001 is a company with eight competitors,
// five of them public, and the sample report (open to everyone).
// WP-156: Pro has the eligibility pack, Consultant the supplier map's CSV as well
// WP-160: Pro has the full list of contracts ending soon, Consultant its CSV as well; WP-162: Pro has the supplier report
const PRO = ['saved_searches', 'email_alerts', 'company_report', 'competitors_full', 'signals_full', 'eligibility_export', 'expiring_contracts', 'sell_report'];
const REPORT_SESSIONS = {
  ['a'.repeat(43)]: PRO, ['b'.repeat(43)]: ['saved_searches', 'email_alerts'],
  ['c'.repeat(43)]: [...PRO, 'signals_csv', 'consortium_gaps', 'branded_reports', 'supplier_map_csv', 'expiring_contracts_csv'], ['d'.repeat(43)]: PRO,
};
// ---- WP-160 (e2e/wp160-api.spec.ts): 14 contracts ending soon, one per basis among them (invented). The public answer has the first 10.
const PERIOD0 = { start: null, end: null, endBasis: null, estimatedFrom: null, duration: null, durationUnit: null, renewal: null, renewalsMax: null };
const endingItem = (i) => tender(160_000 + i, {
  title: `Ending contract ${i}`, status: 'closed', statusNative: 'awarded', deadline: '2025-11-01T10:00:00Z',
  awardedTo: i % 3 === 0 ? [{ name: `Fake Winner ${i} GmbH`, slug: null, country: 'DE' }] : [], awardedPersons: 0,
  contractPeriod: i % 2 === 0
    ? { ...PERIOD0, end: `2026-${String(11 + Math.floor(i / 10)).padStart(2, '0')}-${String(10 + (i % 10)).padStart(2, '0')}`, endBasis: 'stated', renewal: i === 0, renewalsMax: i === 0 ? 2 : null }
    : { ...PERIOD0, start: '2025-11-15', end: `2026-${String(11 + Math.floor(i / 10)).padStart(2, '0')}-${String(10 + (i % 10)).padStart(2, '0')}`, endBasis: 'computed', duration: 12, durationUnit: 'MONTH' },
});
const ENDING = Array.from({ length: 14 }, (_, i) => endingItem(i));
const ending = (items, over = {}) => ({
  within: 12, from: '2026-10-12', to: '2027-10-12', estimated: false, items, total: ENDING.length, offset: 0, freeRows: 10, public: true,
  coverage: [{ country: 'DE', dated: 9613, estimated: 40 }, { country: 'FR', dated: 1423, estimated: 0 }], ...over,
});
// ---- WP-156 (e2e/wp156-api.spec.ts): the supplier map's list and its export, and the open calls of the eligibility pack. Invented names.
const mapSupplier = (id, name, values = []) => ({ id: String(id), slug: `${id}-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`, name, country: 'DE',
  awardCount: 3, firstYear: 2024, lastYear: 2026, cpvDivisions: ['35'], contractValues: values });
const MAP = [mapSupplier(156001, 'Fake Map GmbH', [{ currency: 'EUR', amount: 1_250_000.4, count: 2, lotEstimates: 0 }]), mapSupplier(156002, '=Fake Formula AG')];
const packFact = (value, quote) => ({ value, note: null, quote, scope: 'call_document' });
const packCall = (id, title, facts, deadline = '2026-11-20T17:00:00Z') => ({
  id: String(id), slug: `${id}-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`, title, programme: 'HORIZON', programmeName: 'Horizon Europe',
  topicId: `HORIZON-CL3-2026-${id}`, deadline, deadlineIsDate: false, rolling: false, sourceUrl: `https://ec.europa.eu/info/funding-tenders/opportunities/portal/${id}`,
  sourceName: 'EU Funding & Tenders Portal', fit: facts ? { state: 'read', programme: 'HORIZON', topic: `HORIZON-CL3-2026-${id}`, facts } : { state: 'not_read', programme: 'HORIZON', topic: `HORIZON-CL3-2026-${id}`, facts: {} },
});
const OPEN_FACTS = { eligible_countries: packFact('Legal entities established in EU Member States', 'Applicants must be established in an EU Member State.'),
  consortium_required: packFact(false, 'A single applicant may apply.'), sme_only: packFact(false, 'Open to all.'), ownership_control_restriction: packFact(false, 'No restriction applies.') };
const PACK = {
  items: [packCall(156101, 'Border sensing pilot', OPEN_FACTS), packCall(156102, 'SME cyber resilience', { ...OPEN_FACTS, sme_only: packFact(true, 'Only SMEs may apply.') }, '2026-12-01T17:00:00Z'),
    packCall(156103, 'Unread call', null, '2026-12-15T17:00:00Z')],
  total: 3, cap: 1000, asOf: '2026-10-12T08:00:00Z',
};
const SAMPLE_SLUG = '155001-fake-prime-sa';
const PLAN_OF = { ['a'.repeat(43)]: 'pro', ['b'.repeat(43)]: 'free', ['c'.repeat(43)]: 'consultant', ['d'.repeat(43)]: 'pro' };
const reportSupplier = (slug = REPORT_SLUG, name = 'Fake Defence GmbH') => ({
  id: slug.split('-')[0], slug, name, country: 'DE', awardCount: 12, firstYear: 2024, lastYear: 2026, cpvDivisions: ['35'],
  values: { byCurrency: [{ currency: 'EUR', amount: 4_500_000, count: 3, lotEstimates: 0 }], of: 12, withoutValue: 9, shared: 2, suspect: 0, frameworks: [], estimates: [], largest: [] },
  byYear: [{ year: 2026, awards: 5 }, { year: 2025, awards: 7 }], byCpv: [{ division: '35', awards: 12 }],
  buyers: [{ slug: '5-fake-buyer', name: 'Fake Defence Buyer', country: 'DE', awards: 9 }], notices: [], noticeCount: 12,
  namesAsStated: ['Fake Defence GmbH'], identifiers: [], attribution: 'Source: TED (Tenders Electronic Daily), © European Union.',
});
const reportCompetition = () => ({
  available: true, asOf: '2026-10-12T06:00:00Z', since: '2023-10-12', contracts: 12, markets: 3, competitorCount: 2,
  competitors: [
    { slug: '152002-fake-rival-ag', name: 'Fake Rival AG', country: 'DE', overlap: 7, markets: 2, buyers: 1, ours: 9, sameName: false, sameGroup: null },
    { slug: '152003-fake-defence-gmbh', name: 'Fake Defence GmbH', country: 'DE', overlap: 2, markets: 1, buyers: 1, ours: 4, sameName: true, sameGroup: null },
  ],
  byCountry: [{ key: 'DE', contracts: 10 }, { key: 'PL', contracts: 2 }], byClass: [{ key: '3541', contracts: 8 }, { key: '3530', contracts: 4 }],
  size: { currency: 'EUR', median: 1_500_000, valued: 3, otherCurrencies: 0 }, withoutValue: 9,
  shareByClass: [{ key: '3541', contracts: 8, total: 250, currency: 'EUR', value: 4_500_000, valued: 3, valueTotal: 900_000_000, valuedTotal: 70 }],
  shareByCountry: [{ key: 'DE', contracts: 10, total: 1_900, currency: 'EUR', value: 4_500_000, valued: 3, valueTotal: 2_100_000_000, valuedTotal: 410 }],
  reportOpen: true, sampleReport: SAMPLE_SLUG, isSample: false,
});
const rival = (i) => ({ slug: `15510${i}-fake-rival-${i}-ag`, name: `Fake Rival ${i} AG`, country: 'DE', overlap: 10 - i, markets: 1, buyers: 1, ours: 3, sameName: false, sameGroup: null });
const primeCompetition = (full) => ({
  ...reportCompetition(), competitorCount: 8, competitors: Array.from({ length: full ? 8 : 5 }, (_, i) => rival(i)), full, isSample: true,
});
const signalRow = (i, small) => ({
  company: { id: String(15520 + i), slug: `${15520 + i}-${small ? 'small' : 'large'}-company-${i}`, name: `${small ? 'Small' : 'Large'} Company ${i}`, country: 'NO' },
  recent: 3, prior: 0, recentValues: [], priorValues: [], comparable: null, latest: null,
});
const signal = (items, over = {}) => ({
  kind: 'growing', asOf: '2026-10-12', recentFrom: '2025-10-12', priorFrom: '2024-10-12', windowFrom: '2023-10-12', minRecent: 2,
  items, total: 14, offset: 0, fullOpen: true, freeRows: 10, note: 'Facts from public records, not investment advice.', public: false, smallBelow: 10,
  sources: [{ code: 'ted', name: 'TED', attribution: 'Source: TED, © European Union.' }], ...over,
});
const reportPartners = () => ({
  organisation: { id: '152001', slug: REPORT_SLUG, name: 'Fake Defence GmbH', country: 'DE' }, total: 1, countries: 1, page: 1, pageSize: 20,
  note: 'Partners are the organisations that were active in a project this organisation was active in.',
  items: [{ organisation: { id: '152010', slug: '152010-fake-research-institute', name: 'Fake Research Institute', country: 'FR' }, shared: 2, firstYear: 2022, lastYear: 2024,
    programmes: ['EDF'], projects: [] }],
});
const reportMe = (features, session) => ({ id: 'u152', email: 'ann@example.test', createdAt: '2026-10-22T08:00:00Z',
  profile: { role: 'consultant', tracks: ['tenders'], countries: [], scope: 'core', cadence: 'daily', reportName: session === 'c'.repeat(43) ? 'Acme Advisory Ltd' : null },
  onboarded: true, lastVisitAt: null,
  terms: { current: true }, security: { hasPassword: true, totp: false }, plan: { current: PLAN_OF[session] ?? 'consultant' }, features });

// ---- WP-162 (e2e/wp162-api.spec.ts): the "Who to sell to" report. The sample is the API's answer for the demo company (production,
// 31 October 2026, anonymous view); FAKE_SELL_REPORT names another answer file to serve instead (web/scripts/sell-report-pdf.mjs prints
// it to PDF). The account's report is the named one; a form with CPV 03111000 gets the report with every section empty.
const fixture = (name) => JSON.parse(readFileSync(new URL(`../fixtures/${name}`, import.meta.url), 'utf-8'));
const SELL = { sample: () => (process.env.FAKE_SELL_REPORT ? JSON.parse(readFileSync(process.env.FAKE_SELL_REPORT, 'utf-8')) : fixture('sell-report-sample.json')),
  named: () => fixture('sell-report-named.json'), empty: () => fixture('sell-report-empty.json') };

function sellRoute(p, session, method, body) {
  const features = REPORT_SESSIONS[session] ?? [];
  if (p === '/v1/account/sell-report/sample') return [200, { ...SELL.named(), sample: true }];
  if (p === '/v1/account/sell-report/profile') return [404, { error: 'not_found' }];
  if (p !== '/v1/account/sell-report' || method !== 'POST') return [404, { error: 'not_found' }];
  if (!features.includes('sell_report')) return [402, { error: 'plan_required', message: 'supplier reports are part of Pro: choose a plan under Billing' }];
  if (session === 'd'.repeat(43)) return [402, { error: 'report_quota', message: 'no supplier reports left this month: 3 of 3 used; the count starts again on 2026-11-01 (UTC)' }];
  let form = {};
  try { form = JSON.parse(body || '{}'); } catch { /* not JSON */ }
  const report = (form.cpv ?? []).includes('03111000') ? SELL.empty() : SELL.named();
  const brand = features.includes('branded_reports') ? { name: 'Acme Advisory Ltd', logo: null } : null;
  return [200, { ...report, sample: false, brand, quota: { used: 1, limit: PLAN_OF[session] === 'pro' ? 3 : null, left: 2, per: 'month', counted: true } }];
}

/** WP-155: the account routes of the plan split (the API's competition.py and signals.py), by session. */
function accountRoute(p, q, session, method, body) {
  const features = REPORT_SESSIONS[session];
  if (!features) return [401, { error: 'unauthenticated' }];
  if (p.startsWith('/v1/account/sell-report')) return sellRoute(p, session, method, body);
  const m = /^\/v1\/account\/suppliers\/([^/]+)\/(competition|report)$/.exec(p);
  if (m && m[2] === 'competition') {
    if (!features.includes('competitors_full')) return [402, { error: 'plan_required', message: 'the full list of competitors is part of Pro' }];
    return [200, m[1] === SAMPLE_SLUG ? primeCompetition(true) : { ...reportCompetition(), full: true }];
  }
  if (m && method === 'POST') {
    const out = { resetsAt: '2026-11-01', reportName: features.includes('branded_reports') ? 'Acme Advisory Ltd' : null };
    if (m[1] === SAMPLE_SLUG) return [200, { ...out, sample: true, counted: false, used: null, limit: null, left: null }];
    if (!features.includes('company_report')) return [402, { error: 'plan_required', message: 'company reports are part of Pro' }];
    if (session === 'd'.repeat(43)) return [402, { error: 'report_quota', message: 'no company reports left this month: 3 of 3 opened; the count starts again on 2026-11-01 (UTC)' }];
    const limit = PLAN_OF[session] === 'pro' ? 3 : null;
    return [200, { ...out, sample: false, counted: true, used: 1, limit, left: limit === null ? null : limit - 1 }];
  }
  if (p === '/v1/account/suppliers/export') {
    if (!features.includes('supplier_map_csv')) return [402, { error: 'plan_required', message: 'the supplier map as CSV is part of Team and Consultant' }];
    return [200, { items: MAP, total: 6200, cap: 5000, placsp: false, asOf: '2026-10-12' }];
  }
  if (p === '/v1/account/eligibility/calls') {
    if (!features.includes('eligibility_export')) return [402, { error: 'plan_required', message: "the eligibility check's results pack is part of Pro" }];
    return [200, PACK];
  }
  if (p === '/v1/account/signals/growing/first') return [200, signal([signalRow(1, true), signalRow(2, true), signalRow(3, false)])];
  if (p === '/v1/account/signals/growing') {
    if (!features.includes('signals_full')) return [402, { error: 'plan_required', message: 'the full list of signals is part of a paid plan' }];
    if (Number(q.get('pageSize') ?? 50) > 100 && !features.includes('signals_csv')) return [402, { error: 'plan_required', message: 'the CSV of a signal is part of Team and Consultant' }];
    const items = Array.from({ length: 14 }, (_, i) => signalRow(i, i < 13));
    return [200, { ...signal(items), page: 1, pageSize: Number(q.get('pageSize') ?? 50), csv: features.includes('signals_csv') }];
  }
  if (p === '/v1/account/contracts/ending') {
    if (!features.includes('expiring_contracts')) return [402, { error: 'plan_required', message: 'the full list of contracts ending soon and its alerts are part of Pro' }];
    if (Number(q.get('pageSize') ?? 50) > 100 && !features.includes('expiring_contracts_csv')) return [402, { error: 'plan_required', message: 'the CSV of contracts ending soon is part of Team and Consultant' }];
    return [200, { ...ending(ENDING), public: false, page: 1, pageSize: Number(q.get('pageSize') ?? 50), csv: features.includes('expiring_contracts_csv') }];
  }
  return [404, { error: 'not_found' }];
}

function route(url, headers = {}, method = 'GET', body = '') {
  const p = url.pathname;
  const q = url.searchParams;
  stats.requests.push(`${p}?${q}`);
  if (p === '/_requests') return [200, stats.requests];
  if (p === '/v1/suppliers') return [200, { items: MAP, total: 6200, page: 1, pageSize: Number(q.get('pageSize') ?? 20), maxOffset: 500, withheld: false, placsp: false }];
  if (p === `/v1/suppliers/${REPORT_SLUG}`) return [200, reportSupplier()];
  if (p === `/v1/suppliers/${REPORT_SLUG}/competition`) return [200, reportCompetition()];
  if (p === `/v1/organisations/${REPORT_SLUG}/partners`) return [200, reportPartners()];
  if (p === `/v1/suppliers/${SAMPLE_SLUG}`) return [200, reportSupplier(SAMPLE_SLUG, 'Fake Prime SA')];
  if (p === `/v1/suppliers/${SAMPLE_SLUG}/competition`) return [200, primeCompetition(false)];
  if (p === `/v1/organisations/${SAMPLE_SLUG}/partners`) return [200, { ...reportPartners(), organisation: { id: '155001', slug: SAMPLE_SLUG, name: 'Fake Prime SA', country: 'DE' } }];
  if (p === '/v1/account/status') return [200, { open: false, billing: false, plansOnSale: true, termsVersion: '2.2', privacyVersion: '1.8' }];
  if (p === '/v1/signals/growing') return [200, signal([signalRow(3, false)], { public: true })];
  if (p === '/v1/account/me') {
    const features = REPORT_SESSIONS[headers['x-dg-session']];
    return features ? [200, reportMe(features, headers['x-dg-session'])] : [401, { error: 'unauthenticated' }];
  }
  if (p.startsWith('/v1/account/')) return accountRoute(p, q, headers['x-dg-session'], method, body);
  if (p === '/v1/sell-report/sample') return [200, SELL.sample()];
  if (p === '/v1/tenders/calendar') return [200, calendar()];
  // WP-127: counts that answer after 5 s (a search word the time box cannot count): the page must not wait for them
  if (p === '/v1/tenders/scope-counts' && q.get('q') === 'slowcounts') return [503, { detail: 'the count took too long; narrow the request' }, 5000];
  if (p === '/v1/tenders/scope-counts') return [200, { relevant: 1522, core: 294, supply: 1274, overlap: 46, capped: false, asOf: '2026-10-12T07:55:00Z' }];
  if (p === '/v1/tenders') return tenders(q);
  if (p === '/v1/tenders/ending') return [200, ending(ENDING.slice(0, 10))];
  // WP-143 (e2e/wp143-api.spec.ts): a notice 777nnn answers "busy" (every connection taken, api.py `_busy`) the first time it is
  // asked; a notice 778nnn always answers a statement time-out (503, Retry-After 5)
  if (/^\/v1\/tenders\/777\d{3}(-[a-z0-9-]*)?$/.test(p) && !busyOnce.has(p)) {
    busyOnce.add(p);
    return [503, { detail: 'the service is busy; retry shortly' }, 0, { 'retry-after': '2' }];
  }
  // WP-143 item 13: a buyer withheld as a natural person (410 with the owner's words); 779002 one removed on request
  if (/^\/v1\/buyers\/779001(-[a-z0-9-]*)?$/.test(p)) return [410, { detail: 'Name not shown: it identifies a private person.' }];
  if (/^\/v1\/buyers\/779002(-[a-z0-9-]*)?$/.test(p)) return [410, { detail: 'removed on request' }];
  if (/^\/v1\/buyers\/779003(-[a-z0-9-]*)?$/.test(p)) return [200, OUTSIDE_BUYER];
  if (/^\/v1\/buyers\/779003(-[a-z0-9-]*)?\/suppliers$/.test(p)) return [200, { items: [], suppliers: 0, contracts: 0, attribution: 'TED', cpv: [] }];
  if (/^\/v1\/tenders\/779004(-[a-z0-9-]*)?$/.test(p)) return [200, outsideNotice()];
  if (/^\/v1\/tenders\/778\d{3}(-[a-z0-9-]*)?$/.test(p)) return [503, { detail: 'the query took too long; narrow the request' }, 0, { 'retry-after': '5' }];
  if (/^\/v1\/tenders\/\d+/.test(p) && !p.endsWith('/versions')) {
    const n = Number(/^\/v1\/tenders\/(\d+)/.exec(p)[1]);
    return [200, tender(n, n % 2 ? { source: { ...SRC, lastChangeKind: 'amendment' }, versionCount: 3, amended: true } : {})];
  }
  if (p === '/v1/changes') return [200, changes(q)];
  if (p === '/v1/digest') return q.get('week') === '2026-W42' ? [200, digest('2026-W42')] : [404, {}];
  if (p === '/v1/digest/weeks') return [200, [{ week: '2026-W42', weekFrom: '2026-10-12T00:00:00Z', weekTo: '2026-10-19T00:00:00Z', counts: null, computedAt: null }]];
  if (p === '/v1/sources') return [200, sources()];
  if (p === '/v1/funding' && q.get('q') === 'wp132') {
    // WP-145b: none of these carries the no-funding label: `uaNoFundingTotal` is 0 and the filter `uaNoFunding=true` keeps nothing
    const items = [FUNDING[9002], FUNDING[9003], FUNDING[9004], FUNDING[9005]].map(({ outOfScope, ...c }) => c)
      .filter((c) => q.get('uaNoFunding') !== 'true' || c.ukraineNoFunding);
    return [200, { items: Number(q.get('page') ?? 1) === 1 ? items : [], total: items.length, page: Number(q.get('page') ?? 1), pageSize: Number(q.get('pageSize') ?? 10), uaNoFundingTotal: 0, meta: { updatedAt: NOW } }];
  }
  if (p === '/v1/funding' && q.get('q') === 'wp145') {
    // the API's filter `uaNoFunding=true`: only the calls whose document says it (funding.py)
    const items = [FUNDING[9005], FUNDING[9006]].filter((c) => q.get('uaNoFunding') !== 'true' || c.ukraineNoFunding);
    // WP-145b: the labelled calls among those that match every filter but this one (funding.py `uaNoFundingTotal`): 9006
    return [200, { items, total: items.length, page: 1, pageSize: Number(q.get('pageSize') ?? 10), uaNoFundingTotal: 1, meta: { updatedAt: NOW } }];
  }
  if (p === '/v1/funding') return [200, { items: [], total: 0, page: 1, pageSize: Number(q.get('pageSize') ?? 10) }];
  if (/^\/v1\/funding\/\d+/.test(p)) {
    const c = FUNDING[Number(/^\/v1\/funding\/(\d+)/.exec(p)[1])];
    return c ? [200, c] : [404, { detail: 'no such call' }];
  }
  return [404, { detail: 'not here' }];
}

createServer((req, res) => {
  let sent = '';
  req.on('data', (c) => { sent += c; });
  req.on('end', () => {
    const [status, body, delay = 0, headers = {}] = route(new URL(req.url ?? '/', 'http://x'), req.headers, req.method, sent);
    setTimeout(() => {
      res.writeHead(status, { 'content-type': 'application/json', ...headers });
      res.end(JSON.stringify(body));
    }, delay);
  });
}).listen(PORT, '127.0.0.1', () => console.log(`fake API on ${PORT}`));
