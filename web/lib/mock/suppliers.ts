/**
 * Mock of /v1/suppliers, /v1/suppliers/summary and /v1/suppliers/{slug}, for a build with no API (DG_API_URL unset): five invented
 * companies, so the supplier pages have something to lay out in the demo build and in the end-to-end tests. Shapes only; the numbers
 * are made up, which is why this is never used with an API configured.
 */
import type { Paginated, Supplier, SupplierFilters, SupplierItem, SupplierNotice, SupplierSummary } from '../types';

const ITEMS: SupplierItem[] = [
  { id: '1', slug: '1-demo-airframes-gmbh', name: 'Demo Airframes GmbH', country: 'DE', awardCount: 14, firstYear: 2023, lastYear: 2026, cpvDivisions: ['35', '34'] },
  { id: '2', slug: '2-demo-ordnance-sa', name: 'Demo Ordnance SA', country: 'FR', awardCount: 9, firstYear: 2024, lastYear: 2026, cpvDivisions: ['35'] },
  { id: '3', slug: '3-demo-protective-textiles-sp-z-o-o', name: 'Demo Protective Textiles sp. z o.o.', country: 'PL', awardCount: 6, firstYear: 2024, lastYear: 2025, cpvDivisions: ['35', '18'] },
  { id: '4', slug: '4-demo-logistics-bv', name: 'Demo Logistics B.V.', country: 'NL', awardCount: 3, firstYear: 2025, lastYear: 2026, cpvDivisions: ['63'] },
  { id: '5', slug: '5-demo-sensors-sl', name: 'Demo Sensors S.L.', country: 'ES', awardCount: 2, firstYear: 2026, lastYear: 2026, cpvDivisions: ['35', '38'] },
];

export function querySuppliers(f: SupplierFilters): Paginated<SupplierItem> {
  const q = (f.q ?? '').trim().toLowerCase();
  const countries = (f.country ?? '').split(',').filter(Boolean);
  const cpv = (f.cpv ?? '').split(',').filter(Boolean);
  // every demo supplier has the same three demo buyers (findSupplier): a buyer country among theirs keeps them all
  const buyers = (f.buyerCountry ?? '').split(',').filter(Boolean);
  let items = ITEMS.filter((s) => (!q || s.name.toLowerCase().includes(q))
    && (countries.length === 0 || countries.includes(s.country))
    && (buyers.length === 0 || buyers.some((b) => ['FR', 'DE', 'PL'].includes(b)))
    && (cpv.length === 0 || cpv.some((c) => s.cpvDivisions.some((d) => d.startsWith(c.slice(0, 2))))));
  if (f.sort === 'name') items = [...items].sort((a, b) => a.name.localeCompare(b.name));
  return { items, total: items.length, page: 1, pageSize: f.pageSize ?? 20 };
}

export function supplierSummary(): SupplierSummary {
  return {
    kMin: 1, since: '2023-10-12', noticesRead: 4200, noticesWithSupplier: 31, suppliers: ITEMS.length, awards: 34, skippedNaturalPersons: 2,
    firstPublished: '2023-11-02T00:00:00Z', lastPublished: '2026-10-09T00:00:00Z',
    byCpv: [{ key: '35', suppliers: 4, awards: 31 }, { key: '34', suppliers: 3, awards: 18 }, { key: '63', suppliers: 3, awards: 7 }],
    byCountry: [{ key: 'DE', suppliers: 5, awards: 22 }, { key: 'FR', suppliers: 4, awards: 15 }, { key: 'PL', suppliers: 3, awards: 9 }],
    cells: [], suppressedGroups: 0, coverage: 'Demo data.',
    sources: [{ code: 'ted', name: 'TED (Tenders Electronic Daily)', attribution: 'Source: TED (Tenders Electronic Daily), © European Union.' }],
  };
}

export function findSupplier(slug: string): Supplier | null {
  const id = /^(\d+)(?:-|$)/.exec(slug)?.[1];
  const s = id ? ITEMS.find((x) => x.id === id) : undefined;
  if (!s) return null;
  const valued = Math.min(3, s.awardCount);       // the listed notices 0, 2, 4 name one winner and state a value (below)
  return {
    ...s,
    values: {
      byCurrency: [{ currency: 'EUR', amount: [1_200_000, 1_500_000, 1_800_000].slice(0, valued).reduce((a, b) => a + b, 0), count: valued, lotEstimates: 0 }],
      of: s.awardCount, withoutValue: s.awardCount - valued, shared: Math.min(3, s.awardCount - valued),
      // WP-87: a contract whose published value is a unit price (the 7th row below), in no sum. A further contract of the
      // supplier's beyond the rows the demo lists, so the counts above stay as they were.
      suspect: 1,
    },
    byYear: [{ year: 2023, awards: 1 }, { year: 2024, awards: 4 }, { year: 2025, awards: 6 }, { year: 2026, awards: s.awardCount - 11 > 0 ? s.awardCount - 11 : 1 }],
    byCpv: s.cpvDivisions.map((d, i) => ({ division: d, awards: Math.max(1, s.awardCount - i * 3) })),
    buyers: [
      { slug: '1-demo-armaments-agency', name: 'Demo Armaments Agency', country: 'FR', awards: 6 },
      { slug: '2-demo-defence-materiel-administration', name: 'Demo Defence Materiel Administration', country: 'DE', awards: 5 },
      { slug: '3-demo-logistics-and-support-command', name: 'Demo Logistics and Support Command', country: 'PL', awards: 3 },
    ],
    notices: Array.from({ length: 6 }, (_, i): SupplierNotice => ({
      id: String(900 + i), slug: String(900 + i), noticeId: `2026/S 0${i + 1}0-00${i}`, title: `Framework agreement for demonstration item ${i + 1}`,
      buyerName: i % 3 === 0 ? 'Demo Armaments Agency' : 'Demo Defence Materiel Administration', buyerCountry: i % 3 === 0 ? 'FR' : 'DE',
      publishedAt: `2026-0${(i % 9) + 1}-1${i}T00:00:00Z`, cpv: '35120000', winnersInNotice: i % 2 === 0 ? 1 : 3,
      valueAmount: i % 2 === 0 ? 1_200_000 + i * 150_000 : null, valueCurrency: i % 2 === 0 ? 'EUR' : null, sourceUrl: null,
    })).concat([{
      // WP-87: "EUR 48 over 1 contract" in the audit: a price per item published as the value
      id: '906', slug: '906', noticeId: '2026/S 070-006', title: 'Supply of fasteners at a unit price', buyerName: 'Demo Armaments Agency',
      buyerCountry: 'FR', publishedAt: '2026-07-16T00:00:00Z', cpv: '35120000', winnersInNotice: 1, valueAmount: 48, valueCurrency: 'EUR',
      valueSuspect: true, sourceUrl: null,
    }]),
    noticeCount: s.awardCount, namesAsStated: [s.name, s.name.toUpperCase()], identifiers: [`DE${100000000 + Number(s.id)}`],
    attribution: 'Source: TED, © European Union.',
  };
}
