// A fake of the parts of the API that WP-52b reads, shaped as docs/design/API_CONTRACT.md ("Changes of 19 October 2026") says, with the
// numbers of the UX audit of 19 October 2026: 1,449 open notices with a deadline (593 in November), 287,634 closed notices that stop at
// position 10,000, 2,311 changes in 14 days (3,100 for Poland), a digest week of 873 new notices. For e2e/wp52b-api.spec.ts, e2e/wp127-api.spec.ts and
// e2e/wp132-api.spec.ts (five funding calls, 9001-9005); nothing else uses it.
//
// `npx playwright test` against a local build starts it and a second `next start` that reads it (playwright.config.ts, the
// fake-api-* projects, WP-128). By hand, against a site of your own:
//   node e2e/support/fake-api.mjs [port]              then:  DG_API_URL=http://127.0.0.1:4010 npx next start -p 3100
//   E2E_FAKE_API=1 E2E_BASE_URL=http://127.0.0.1:3100 npx playwright test e2e/wp52b-api.spec.ts
//
// Every path it does not know answers 404 (the site treats that as "no such record"). Dates are relative to the pinned site clock
// (NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z, the CI build): the calendar's deadlines are from 20 October on.
import { createServer } from 'node:http';

const PORT = Number(process.argv[2] ?? process.env.FAKE_API_PORT ?? 4010);
const NOW = '2026-10-12T08:00:00Z';
const SRC = { sourceId: 'ted', sourceName: 'TED', url: 'https://ted.europa.eu/en/notice/-/detail/1', retrievedAt: '2026-10-11T06:20:00Z', lastChangeKind: 'first_seen', licence: 'Commission Decision 2011/833/EU', attribution: '© European Union, TED' };
const stats = { requests: [] };

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

function tenders(q) {
  const status = q.get('status') ?? 'open';
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
};

function route(url) {
  const p = url.pathname;
  const q = url.searchParams;
  stats.requests.push(`${p}?${q}`);
  if (p === '/_requests') return [200, stats.requests];
  if (p === '/v1/tenders/calendar') return [200, calendar()];
  // WP-127: counts that answer after 5 s (a search word the time box cannot count): the page must not wait for them
  if (p === '/v1/tenders/scope-counts' && q.get('q') === 'slowcounts') return [503, { detail: 'the count took too long; narrow the request' }, 5000];
  if (p === '/v1/tenders/scope-counts') return [200, { relevant: 1522, core: 294, supply: 1274, overlap: 46, capped: false, asOf: '2026-10-12T07:55:00Z' }];
  if (p === '/v1/tenders') return tenders(q);
  if (/^\/v1\/tenders\/\d+/.test(p) && !p.endsWith('/versions')) {
    const n = Number(/^\/v1\/tenders\/(\d+)/.exec(p)[1]);
    return [200, tender(n, n % 2 ? { source: { ...SRC, lastChangeKind: 'amendment' }, versionCount: 3, amended: true } : {})];
  }
  if (p === '/v1/changes') return [200, changes(q)];
  if (p === '/v1/digest') return q.get('week') === '2026-W42' ? [200, digest('2026-W42')] : [404, {}];
  if (p === '/v1/digest/weeks') return [200, [{ week: '2026-W42', weekFrom: '2026-10-12T00:00:00Z', weekTo: '2026-10-19T00:00:00Z', counts: null, computedAt: null }]];
  if (p === '/v1/sources') return [200, sources()];
  if (p === '/v1/funding' && q.get('q') === 'wp132') {
    const items = [FUNDING[9002], FUNDING[9003], FUNDING[9004], FUNDING[9005]].map(({ outOfScope, ...c }) => c);
    return [200, { items: Number(q.get('page') ?? 1) === 1 ? items : [], total: items.length, page: Number(q.get('page') ?? 1), pageSize: Number(q.get('pageSize') ?? 10), meta: { updatedAt: NOW } }];
  }
  if (p === '/v1/funding') return [200, { items: [], total: 0, page: 1, pageSize: Number(q.get('pageSize') ?? 10) }];
  if (/^\/v1\/funding\/\d+/.test(p)) {
    const c = FUNDING[Number(/^\/v1\/funding\/(\d+)/.exec(p)[1])];
    return c ? [200, c] : [404, { detail: 'no such call' }];
  }
  return [404, { detail: 'not here' }];
}

createServer((req, res) => {
  const [status, body, delay = 0] = route(new URL(req.url ?? '/', 'http://x'));
  setTimeout(() => {
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body));
  }, delay);
}).listen(PORT, '127.0.0.1', () => console.log(`fake API on ${PORT}`));
