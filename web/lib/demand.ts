/**
 * The demand map of the supplier report (WP-66): who in defence buys what the company makes, from the CPV codes of the supplier page.
 * The one call: `POST /api/readiness/demand` with the codes and the five countries, and nothing else of the profile. The server keeps
 * nothing. Pure except `fetchDemand`.
 */
import type { Profile } from './profile';

export const DEMAND_COUNTRIES = ['ES', 'DE', 'FR', 'PL', 'NL'] as const;

export interface DemandRequest { cpv: string[]; countries: string[] }

export interface DemandRef {
  id: string; slug: string; noticeId: string; title: string; buyerName: string | null; publishedAt: string | null;
  source: string; sourceUrl: string | null; directive: boolean;
}
export interface DemandBuyer { slug: string; name: string; core: boolean; procurements: number }
export interface DemandWinner { name: string; country: string; awards: number; notices: DemandRef[] }
export interface DemandCounts { procurements: number; directive: number; coreBuyers: number; otherBuyers: number; awarded: number; winners: number }
export interface DemandCountry extends DemandCounts {
  country: string; topBuyers: DemandBuyer[]; topWinners: DemandWinner[]; otherWinners: { winners: number; awards: number }; latest: DemandRef[];
}
export interface Demand {
  since: string; until: string; kMin: number; countries: string[];
  codes: { code: string; prefix: string; procurements: number }[];
  total: DemandCounts; byCountry: DemandCountry[];
  coverage: string; winnersFrom: string; notice: string;
  sources: { code: string; name: string; attribution: string; lastUpdated?: string | null }[];
}

/** The request for a profile: its CPV codes (at most 15, as the supplier page keeps them) and the five countries; null without codes. */
export function demandRequest(p: Profile): DemandRequest | null {
  const cpv = p.supplier.cpv.filter((c) => /^\d{8}$/.test(c)).slice(0, 15);
  return cpv.length ? { cpv, countries: [...DEMAND_COUNTRIES] } : null;
}

/** "12 of 150 (8 %)"; a share of nothing is not a share. */
export function directiveShare(c: Pick<DemandCounts, 'directive' | 'procurements'>): string {
  if (c.procurements === 0) return 'none';
  return `${c.directive} of ${c.procurements} (${Math.round((100 * c.directive) / c.procurements)} %)`;
}

/** "3 core defence buyers and 2 other defence-scope buyers". */
export function buyerLine(c: Pick<DemandCounts, 'coreBuyers' | 'otherBuyers'>): string {
  const n = (k: number, what: string) => `${k} ${what}${k === 1 ? '' : 's'}`;
  return `${n(c.coreBuyers, 'core defence buyer')} and ${n(c.otherBuyers, 'other defence-scope buyer')}`;
}

/** The winners not named, in words: the mosaic rule of the supplier map. */
export function otherWinnersLine(c: DemandCountry, kMin: number): string | null {
  const { winners, awards } = c.otherWinners;
  if (winners === 0) return null;
  return `${winners} ${winners === 1 ? 'other winner' : 'other winners'} (${awards} ${awards === 1 ? 'award' : 'awards'}) not named: a winner is named only with ` +
    `at least ${kMin} awards here, and at most ten per country.`;
}

export class DemandError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export const DEMAND_FAILED = 'The demand map could not be computed. Try again in a moment.';

export async function fetchDemand(request: DemandRequest, signal?: AbortSignal): Promise<Demand> {
  const res = await fetch('/api/readiness/demand', {
    method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(request), signal, cache: 'no-store', credentials: 'omit',
  }).catch((e: unknown) => {
    if (signal?.aborted) throw e;
    throw new DemandError(0, DEMAND_FAILED);
  });
  if (!res.ok) throw new DemandError(res.status, res.status === 429 ? 'Too many requests. Wait a minute and try again.' : DEMAND_FAILED);
  return (await res.json()) as Demand;
}
