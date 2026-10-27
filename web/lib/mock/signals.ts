/**
 * Mock of GET /v1/signals/{kind} (WP-154) for a build with no API: invented demo companies (lib/mock/suppliers.ts names), so the
 * page has something to lay out in the demo build and the end-to-end tests. Shapes only; the numbers are made up. The paid part is
 * closed here (`fullOpen: false`), as it is by default.
 */
import type { FundingRow, GrowingRow, MarketRow, SignalAnswer, SignalFilters, SignalKind, SignalRow } from '../signals';

const co = (id: string, name: string, country: string) => ({ id, slug: `${id}-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-$/, '')}`, name, country });
const notice = (id: string, day: string) => ({ id, slug: `${id}-demo-contract`, noticeId: `${id}-2026`, title: 'Demo contract', publishedAt: `${day}T00:00:00Z`, sourceUrl: `https://ted.europa.eu/en/notice/-/detail/${id}-2026`, source: 'ted' });

const GROWING: GrowingRow[] = [
  { company: co('1', 'Demo Airframes GmbH', 'DE'), recent: 9, prior: 4, recentValues: [{ currency: 'EUR', amount: 4_000_000, count: 3 }], priorValues: [{ currency: 'EUR', amount: 500_000, count: 1 }],
    comparable: { currency: 'EUR', recent: 4_000_000, recentCount: 3, prior: 500_000, priorCount: 1 }, latest: notice('101', '2026-09-30') },
  { company: co('2', 'Demo Ordnance SA', 'FR'), recent: 6, prior: 3, recentValues: [{ currency: 'EUR', amount: 12_000_000, count: 2 }], priorValues: [],
    comparable: null, latest: notice('102', '2026-08-14') },
  { company: co('3', 'Demo Protective Textiles sp. z o.o.', 'PL'), recent: 4, prior: 2, recentValues: [{ currency: 'PLN', amount: 7_000_000, count: 2 }], priorValues: [{ currency: 'PLN', amount: 2_000_000, count: 1 }],
    comparable: { currency: 'PLN', recent: 7_000_000, recentCount: 2, prior: 2_000_000, priorCount: 1 }, latest: notice('103', '2026-07-01') },
];
const MARKETS: MarketRow[] = [
  { company: co('1', 'Demo Airframes GmbH', 'DE'), market: 'LT', firstWinAt: '2026-09-02T00:00:00Z', winsThere: 2, winsBefore: 5, firstWin: notice('111', '2026-09-02') },
  { company: co('4', 'Demo Logistics B.V.', 'NL'), market: 'PL', firstWinAt: '2026-06-18T00:00:00Z', winsThere: 1, winsBefore: 2, firstWin: notice('112', '2026-06-18') },
];
const project = (id: string, acronym: string, programme: string, role: string) => ({ slug: `${id}-${acronym.toLowerCase()}`, acronym, title: `${acronym} demo project`, programme, year: 2025, role, source: 'edf_factsheets', factsheetUrl: null });
const FUNDING: FundingRow[] = [
  { company: co('5', 'Demo Sensors S.L.', 'ES'), year: 2025, first: true, newProjects: 1, earlierProjects: 0, projects: [project('201', 'DEMOSENSE', 'EDF', 'participant')] },
  { company: co('1', 'Demo Airframes GmbH', 'DE'), year: 2025, first: false, newProjects: 2, earlierProjects: 3, projects: [project('202', 'DEMOWING', 'EDF', 'coordinator'), project('203', 'DEMOLINK', 'EDF', 'participant')] },
];
const ROWS: Record<SignalKind, SignalRow[]> = { growing: GROWING, markets: MARKETS, funding: FUNDING };

export function querySignal(f: Omit<SignalFilters, 'page'>): SignalAnswer {
  const countries = f.country.toUpperCase().split(',').map((c) => c.trim()).filter(Boolean);
  const programmes = f.programme.split(',').filter(Boolean);
  const items = ROWS[f.kind].filter((r) => (countries.length === 0 || countries.includes(r.company.country ?? ''))
    && (programmes.length === 0 || ('projects' in r && r.projects.some((p) => programmes.includes(p.programme)))));
  return {
    kind: f.kind, asOf: '2026-10-12', recentFrom: '2025-10-12', priorFrom: '2024-10-12', windowFrom: '2023-10-12', minRecent: 2,
    items, total: items.length, offset: 0, fullOpen: false, freeRows: 10, note: 'Facts from public records, not investment advice.',
    sources: f.kind === 'funding'
      ? [{ code: 'edf_factsheets', name: 'European Defence Fund: project factsheets of the call results', attribution: null }]
      : [{ code: 'ted', name: 'TED (Tenders Electronic Daily)', attribution: 'Source: TED (Tenders Electronic Daily), © European Union.' }],
  };
}
