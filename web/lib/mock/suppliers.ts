/**
 * Mock of /v1/suppliers, /v1/suppliers/summary and /v1/suppliers/{slug}, for a build with no API (DG_API_URL unset): five invented
 * companies, so the supplier pages have something to lay out in the demo build and in the end-to-end tests. Shapes only; the numbers
 * are made up, which is why this is never used with an API configured.
 */
import type { BuyerSuppliers, Paginated, Supplier, SupplierContract, SupplierContracts, SupplierFilters, SupplierItem, SupplierNotice, SupplierSummary } from '../types';

const ITEMS: SupplierItem[] = [
  { id: '1', slug: '1-demo-airframes-gmbh', name: 'Demo Airframes GmbH', country: 'DE', awardCount: 14, firstYear: 2023, lastYear: 2026, cpvDivisions: ['35', '34'] },
  { id: '2', slug: '2-demo-ordnance-sa', name: 'Demo Ordnance SA', country: 'FR', awardCount: 9, firstYear: 2024, lastYear: 2026, cpvDivisions: ['35'] },
  { id: '3', slug: '3-demo-protective-textiles-sp-z-o-o', name: 'Demo Protective Textiles sp. z o.o.', country: 'PL', awardCount: 6, firstYear: 2024, lastYear: 2025, cpvDivisions: ['35', '18'] },
  { id: '4', slug: '4-demo-logistics-bv', name: 'Demo Logistics B.V.', country: 'NL', awardCount: 3, firstYear: 2025, lastYear: 2026, cpvDivisions: ['63'] },
  { id: '5', slug: '5-demo-sensors-sl', name: 'Demo Sensors S.L.', country: 'ES', awardCount: 2, firstYear: 2026, lastYear: 2026, cpvDivisions: ['35', '38'] },
];

/** WP-98b: the list's contract values of each demo company (invented), per currency; the Spanish one's wins are PLACSP's (no TED view). */
const VALUES: Record<string, SupplierItem['contractValues']> = {
  1: [{ currency: 'EUR', amount: 4_500_000, count: 3, lotEstimates: 0 }],
  2: [{ currency: 'EUR', amount: 12_000_000, count: 2, lotEstimates: 0 }],
  3: [{ currency: 'PLN', amount: 7_000_000, count: 2, lotEstimates: 0 }, { currency: 'EUR', amount: 250_000, count: 1, lotEstimates: 0 }],
  4: [],
  5: [{ currency: 'EUR', amount: 300_000, count: 1, lotEstimates: 0 }],
};
const sumIn = (s: SupplierItem, cur: string) => s.contractValues?.find((v) => v.currency === cur)?.amount;

export function querySuppliers(f: SupplierFilters): Paginated<SupplierItem> {
  const q = (f.q ?? '').trim().toLowerCase();
  const countries = (f.country ?? '').split(',').filter(Boolean);
  const cpv = (f.cpv ?? '').split(',').filter(Boolean);
  // every demo supplier has the same three demo buyers (findSupplier): a buyer country among theirs keeps them all
  const buyers = (f.buyerCountry ?? '').split(',').filter(Boolean);
  // WP-96: a curated group's members are, in the demo data, the companies whose name begins with the group's key
  let items = ITEMS.map((s) => ({ ...s, contractValues: VALUES[s.id] ?? [] })).filter((s) => (!q || s.name.toLowerCase().includes(q))
    && (f.source !== 'ted' || s.country !== 'ES')
    && (!f.group || s.name.toLowerCase().startsWith(f.group))
    && (countries.length === 0 || countries.includes(s.country))
    && (buyers.length === 0 || buyers.some((b) => ['FR', 'DE', 'PL'].includes(b)))
    && (cpv.length === 0 || cpv.some((c) => s.cpvDivisions.some((d) => d.startsWith(c.slice(0, 2))))));
  if (f.sort === 'name') items = [...items].sort((a, b) => a.name.localeCompare(b.name));
  const cur = f.sort?.startsWith('value-') ? f.sort.slice(6) : null;
  if (cur) items = [...items].sort((a, b) => (sumIn(b, cur) ?? -1) - (sumIn(a, cur) ?? -1) || b.awardCount - a.awardCount);
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

export function findSupplier(slug: string, under: { cpv?: string; buyerCountry?: string } = {}): Supplier | null {
  const id = /^(\d+)(?:-|$)/.exec(slug)?.[1];
  const s = id ? ITEMS.find((x) => x.id === id) : undefined;
  if (!s) return null;
  // WP-89: the demo's count under the asked codes: its contracts in the divisions asked (each division of the item holds a share)
  const asked = (under.cpv ?? '').split(',').map((c) => c.trim()).filter((c) => /^\d{2,8}$/.test(c));
  const underCodes = asked.length ? {
    cpv: asked.map((c) => (c.length === 8 ? c.replace(/0+$/, '').padEnd(2, '0') : c)),
    buyerCountries: (under.buyerCountry ?? '').split(',').map((c) => c.trim().toUpperCase()).filter(Boolean),
    contracts: Math.max(0, Math.floor(s.awardCount * s.cpvDivisions.filter((d) => asked.some((c) => c.startsWith(d))).length / Math.max(1, s.cpvDivisions.length))),
  } : null;
  const valued = Math.min(3, s.awardCount);       // the listed notices 0, 2, 4 name one winner and state a value (below)
  return {
    ...s,
    underCodes,
    // WP-96: the demo's curated group, of every demo company (querySuppliers reads `group` as a name prefix)
    group: s.id === '1' ? { key: 'demo', name: 'Demo', source: 'Demo group list (demo data)', members: ITEMS.length } : null,
    values: {
      byCurrency: [{ currency: 'EUR', amount: [1_200_000, 1_500_000, 1_800_000].slice(0, valued).reduce((a, b) => a + b, 0), count: valued, lotEstimates: 0 }],
      of: s.awardCount, withoutValue: s.awardCount - valued, shared: Math.min(3, s.awardCount - valued),
      // WP-87: a contract whose published value is a unit price (the 7th row below), in no sum. A further contract of the
      // supplier's beyond the rows the demo lists, so the counts above stay as they were.
      suspect: 1,
      // WP-95: a framework ceiling, listed apart and never added (a further contract beyond the rows listed, as above), and the
      // largest contract values: the valued rows below, the largest first
      frameworks: [{ currency: 'EUR', amount: 5_000_000, count: 1, lotEstimates: 0 }],
      estimates: [],
      largest: [4, 2, 0].slice(3 - valued).map((i) => ({
        id: String(900 + i), slug: String(900 + i), noticeId: `2026/S 0${i + 1}0-00${i}`, title: `Framework agreement for demonstration item ${i + 1}`,
        buyerName: i % 3 === 0 ? 'Demo Armaments Agency' : 'Demo Defence Materiel Administration', publishedAt: `2026-0${(i % 9) + 1}-1${i}T00:00:00Z`,
        amount: 1_200_000 + i * 150_000, currency: 'EUR', sourceUrl: null, source: 'ted',
      })),
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
      valueKind: i % 2 === 0 ? 'contract' : null,
      // WP-95: a call-off that names its framework agreement
      framework: i === 2 ? { source: 'ted', noticeId: '2026/S 010-000', sourceUrl: null, slug: '900' } : null,
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

/** WP-100: GET /v1/suppliers/{slug}/contracts in the demo: the profile's notices, one contract each, with TED's licence. */
export function supplierContracts(slug: string): SupplierContracts | null {
  const s = findSupplier(slug);
  if (!s) return null;
  const items: SupplierContract[] = s.notices.map((n) => ({
    noticeId: n.noticeId, slug: n.slug, title: n.title, buyerName: n.buyerName, buyerCountry: n.buyerCountry, publishedAt: n.publishedAt,
    cpv: n.cpv, winnersInNotice: n.winnersInNotice, valueAmount: n.valueAmount, valueCurrency: n.valueCurrency, valueKind: n.valueAmount === null ? null : n.valueKind ?? 'contract',
    inContractSum: n.valueAmount !== null && (n.valueKind ?? 'contract') === 'contract' && !n.valueSuspect,
    frameworkNoticeId: n.framework?.noticeId ?? null, source: n.source ?? 'ted', sourceName: 'TED (Tenders Electronic Daily)', sourceUrl: n.sourceUrl,
    licence: 'Commission Decision 2011/833/EU (reuse permitted with attribution)', attribution: 'Source: TED, © European Union.',
  }));
  return { slug: s.slug, name: s.name, total: items.length, cap: 5000, items };
}

/**
 * WP-90: GET /v1/buyers/{slug}/suppliers in the demo: the demo suppliers whose profile lists the buyer (findSupplier's three demo
 * buyers), with fewer contracts the later the supplier comes, most first.
 */
export function buyerSuppliers(buyer: { slug: string }): BuyerSuppliers {
  const items = ITEMS.flatMap((s) => {
    const row = findSupplier(s.slug)?.buyers.find((b) => b.slug === buyer.slug);
    return row ? [{ slug: s.slug, name: s.name, country: s.country, awards: Math.max(1, row.awards - Number(s.id) + 1) }] : [];
  }).sort((a, b) => b.awards - a.awards || a.name.localeCompare(b.name));
  return {
    items, suppliers: items.length, contracts: items.reduce((n, s) => n + s.awards, 0),
    attribution: 'Source: TED (Tenders Electronic Daily), © European Union. Winners as named in each notice; natural persons are never named.',
  };
}
