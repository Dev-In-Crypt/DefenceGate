/**
 * Mock of /v1/stats/market and /v1/buyers/{slug}/profile, for a build with no API (DG_API_URL unset).
 * Shapes only: the numbers are made up, which is why this is never used with an API configured.
 */
import type { Buyer, BuyerProfile, MarketStats } from '../types';

const BASIS = {
  months: 'Counts of notices published per month, not contract value. Source coverage differs by country: see source status.',
  countries: 'Counts of notices published in the last 12 months, by the buyer\'s country. Source coverage differs by country: see source status.',
  sources: 'Counts of notices published in the last 12 months, by the source we collected them from.',
  amendments: 'Share of the notices published in the last 12 months that have an amendment in the archive.',
  responseWindow: 'Days from publication to the stated deadline, for notices that state one.',
  cpvGroups: 'Notices published in the last 12 months with at least one code in the 3-digit CPV group. Counts of notices, not contract value.',
};

export function marketStats(ref: Date = new Date()): MarketStats {
  const months = Array.from({ length: 36 }, (_, i) => {
    const d = new Date(Date.UTC(ref.getUTCFullYear(), ref.getUTCMonth() - 35 + i, 1));
    const ted = 120 + ((i * 37) % 60);
    return { month: `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`, count: ted + 40 + ((i * 11) % 25), ted, partial: i === 35 };
  });
  return {
    asOf: ref.toISOString(),
    scope: 'core',
    unit: 'notices published',
    windowFrom: new Date(ref.getTime() - 365 * 86_400_000).toISOString().slice(0, 10),
    windowTo: ref.toISOString().slice(0, 10),
    sourceCount: 4,
    months,
    countries: { total: 1900, items: [{ country: 'DE', count: 410 }, { country: 'PL', count: 330 }, { country: 'FR', count: 280 }, { country: 'ES', count: 190 }], other: 690 },
    sources: [{ id: 'ted', name: 'TED', count: 1500 }, { id: 'fr_boamp', name: 'BOAMP', count: 250 }, { id: 'pl_ezam', name: 'e-Zamówienia', count: 150 }],
    amendments: { notices: 1900, amended: 14, share: 0.0074, observedFrom: '2026-09-18T06:00:00Z' },
    responseWindow: { notices: 1500, median: 35, p25: 24, p75: 49 },
    cpvGroups: [{ group: '354', count: 410 }, { group: '351', count: 300 }, { group: '353', count: 220 }],
    basis: BASIS,
    // WP-105: made-up contract values in the API's shape
    money: {
      asOf: ref.toISOString(), since: new Date(ref.getTime() - 365 * 86_400_000).toISOString().slice(0, 10), until: ref.toISOString().slice(0, 10),
      total: { byCurrency: [{ currency: 'EUR', amount: 182_400_000, count: 610, lotEstimates: 0 }, { currency: 'PLN', amount: 96_000_000, count: 120, lotEstimates: 0 }], of: 900, withoutValue: 170 },
      byCountry: [
        { country: 'ES', byCurrency: [{ currency: 'EUR', amount: 98_000_000, count: 420, lotEstimates: 0 }], of: 520, withoutValue: 100 },
        { country: 'PL', byCurrency: [{ currency: 'PLN', amount: 96_000_000, count: 120, lotEstimates: 0 }], of: 160, withoutValue: 40 },
        { country: 'DE', byCurrency: [{ currency: 'EUR', amount: 84_400_000, count: 190, lotEstimates: 0 }], of: 220, withoutValue: 30 },
      ],
      byCpvGroup: [
        { group: '354', byCurrency: [{ currency: 'EUR', amount: 60_000_000, count: 200, lotEstimates: 0 }], of: 240, withoutValue: 40 },
        { group: '351', byCurrency: [{ currency: 'EUR', amount: 22_000_000, count: 90, lotEstimates: 0 }], of: 110, withoutValue: 20 },
      ],
      byBuyer: [
        { slug: '1-demo-armaments-agency', name: 'Demo Armaments Agency', country: 'DE', byCurrency: [{ currency: 'EUR', amount: 40_000_000, count: 80, lotEstimates: 0 }], of: 95, withoutValue: 15 },
      ],
    },
    basisMoney: 'Sums of the contract values awarded, per currency, never converted: the contracts of the supplier map. Framework ceilings, estimates and unit prices are never added.',
  };
}

export function buyerProfile(buyer: Buyer, ref: Date = new Date()): BuyerProfile {
  const year = ref.getUTCFullYear();
  return {
    buyerId: buyer.id,
    asOf: ref.toISOString(),
    tenderCount: buyer.tenderCount,
    openNow: buyer.openCount,
    // WP-87: the years add up to the total: what the six years do not hold is "Before ..."
    perYear: Array.from({ length: 6 }, (_, i) => ({ year: year - 5 + i, count: Math.floor(buyer.tenderCount / 7) })),
    perYearEarlier: buyer.tenderCount - 6 * Math.floor(buyer.tenderCount / 7),
    perYearUndated: 0,
    cpvGroups: [{ group: '354', count: buyer.tenderCount }],
    responseWindow: { notices: buyer.tenderCount, median: 28, p25: 21, p75: 40 },
    // the archive began in September 2026: too short to say how often a buyer amends (WP-87)
    amendments: { notices: buyer.tenderCount, amended: 0, share: 0, observedFrom: '2026-09-18T06:00:00Z' },
    sources: [{ id: 'ted', name: 'TED', count: buyer.tenderCount }],
    basis: {
      perYear: 'Counts of this buyer\'s notices by year of publication, not contract value.',
      cpvGroups: 'This buyer\'s notices, all years, with at least one code in the 3-digit CPV group.',
      responseWindow: 'Days from publication to the stated deadline over this buyer\'s notices that state one.',
      amendments: 'Share of this buyer\'s notices with an amendment in the archive.',
      sources: 'Counts of this buyer\'s notices by the source we collected them from.',
    },
  };
}
