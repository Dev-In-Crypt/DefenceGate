/**
 * The demand map of the supplier report (WP-66): who in defence buys what the company makes, from the CPV codes of the supplier page.
 * The one call: `POST /api/readiness/demand` with the codes and the five countries, and nothing else of the profile. The server keeps
 * nothing. Pure except `fetchDemand`.
 */
import type { Profile } from './profile';
import type { ValueTotals } from './value-totals';

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
/** WP-80: a company that wins these procurements, across the countries asked (WP-81: every legal entity, kMin is 1). */
export interface ApproachWinner {
  name: string; country: string | null; contracts: number;
  /** Its supplier page here. Since WP-85 every winner has one (the map counts the same awards); null only in an answer from before. */
  slug: string | null;
  /** WP-81: the sum of its contracts' values per currency (`of` is `contracts`), collapsed under each winner. */
  values: ValueTotals;
  buyers: { slug: string; name: string; country: string; contracts: number }[];
  /** The publication date of its newest notice (TED: the result notice; PLACSP: the procurement, the award date is not stored). */
  countries: string[]; lastAward: string | null;
  prime: { group: string; jointVenture: boolean; source: string; sourceUrl: string } | null;
  edfProjects: number; defenceBuyer: boolean;
}
export interface Approach {
  winners: ApproachWinner[];
  /** Winners with fewer than kMin procurements: counted, never named (WP-81: kMin is 1, so none; an older answer had kMin 3). */
  below: { winners: number; awards: number };
  /** Winners with kMin or more past the first 30 (a prime is never among them). */
  more: { winners: number; awards: number };
}
export interface Demand {
  since: string; until: string; kMin: number; countries: string[];
  codes: { code: string; prefix: string; procurements: number }[];
  total: DemandCounts; byCountry: DemandCountry[]; approach: Approach;
  coverage: string; winnersFrom: string; notice: string;
  sources: { code: string; name: string; attribution: string; lastUpdated?: string | null }[];
}

/** The request for a profile: its CPV codes (at most 15, as the supplier page keeps them) and the five countries; null without codes. */
export function demandRequest(p: Profile): DemandRequest | null {
  const cpv = p.supplier.cpv.filter((c) => /^\d{8}$/.test(c)).slice(0, 15);
  return cpv.length ? { cpv, countries: [...DEMAND_COUNTRIES] } : null;
}

/**
 * WP-68: the codes of the sample on /readiness/spain-automotive: the vehicle-parts profile of the WP-65/66 samples (the page prints their
 * official titles). The page shows the API's live answer for them, or nothing.
 */
export const SAMPLE_CPV = ['34300000', '34100000', '35421000', '42600000', '44300000'] as const;

/** Whether a body is a demand answer the page can show (a live read from the API, so it is checked before use). */
export function isDemand(d: unknown): d is Demand {
  const x = d as Demand | null;
  return typeof x === 'object' && x !== null && typeof x.since === 'string' && typeof x.until === 'string' && typeof x.coverage === 'string'
    && typeof x.total?.procurements === 'number' && Array.isArray(x.byCountry) && x.byCountry.every((c) => typeof c?.country === 'string' && typeof c.procurements === 'number');
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

/** The winners not listed, in words: the end of the list (WP-81), or the old mosaic rule of an answer with kMin above 1. */
export function otherWinnersLine(c: DemandCountry, kMin: number): string | null {
  const { winners, awards } = c.otherWinners;
  if (winners === 0) return null;
  const head = `${winners} ${winners === 1 ? 'other winner' : 'other winners'} (${awards} ${awards === 1 ? 'award' : 'awards'})`;
  return kMin > 1
    ? `${head} not named: a winner is named only with at least ${kMin} awards here, and at most ten per country.`
    : `${head} not listed here: the list shows the ten with the most awards per country, and the report names them all under Who to approach.`;
}

/** The winners not named in "who to approach", in words: the mosaic rule, and the end of the list. */
export function approachOthersLine(a: Approach, kMin: number): string | null {
  const n = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;
  const parts: string[] = [];
  if (a.below.winners > 0) {
    parts.push(`${n(a.below.winners, 'other winner', 'other winners')} with fewer than ${kMin} awards each (${n(a.below.awards, 'award', 'awards')} together) ` +
      `${a.below.winners === 1 ? 'is' : 'are'} counted, not named.`);
  }
  if (a.more.winners > 0) {
    parts.push(`${n(a.more.winners, 'more winner', 'more winners')} with ${kMin} or more awards (${n(a.more.awards, 'award', 'awards')}) ` +
      `${a.more.winners === 1 ? 'is' : 'are'} not listed: the list stops at 30, and every prime contractor or large defence group is on it.`);
  }
  return parts.length ? parts.join(' ') : null;
}

/** The primes and large defence groups among the named winners, the realistic way in for a subcontractor. */
export function primesOf(a: Approach): ApproachWinner[] {
  return a.winners.filter((w) => w.prime !== null);
}

export class DemandError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export const DEMAND_FAILED = 'The demand map could not be computed. Try again in a moment.';

export async function fetchDemand(request: DemandRequest, signal?: AbortSignal): Promise<Demand> {
  return post<Demand>('/api/readiness/demand', request, signal);
}

/** WP-81: every winner of the demand answer, a page of `pageSize` at a time (POST /v1/readiness/winners). */
export interface WinnersPage {
  since: string; until: string; countries: string[]; total: number; page: number; pageSize: number;
  winners: ApproachWinner[]; winnersFrom: string; sources: Demand['sources'];
}

export async function fetchWinners(request: DemandRequest & { page: number }, signal?: AbortSignal): Promise<WinnersPage> {
  return post<WinnersPage>('/api/readiness/winners', request, signal);
}

/** The page of every winner for the profile's codes: in every country asked, or in one. */
export function winnersHref(country?: string): string {
  return `/readiness/supplier/winners${country ? `?country=${country}` : ''}`;
}

/** "All 496 winners for these codes", the link under a list that stops before the end. */
export function allWinnersLabel(n: number, country?: string): string {
  return `All ${n} ${n === 1 ? 'winner' : 'winners'}${country ? ` in ${country}` : ''} for these codes`;
}

async function post<T>(path: string, request: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, {
    method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(request), signal, cache: 'no-store', credentials: 'omit',
  }).catch((e: unknown) => {
    if (signal?.aborted) throw e;
    throw new DemandError(0, DEMAND_FAILED);
  });
  if (!res.ok) {
    if (res.status === 429) throw new DemandError(429, 'Too many requests. Wait a minute and try again.');
    // WP-80: codes that match too many notices are refused with the API's own sentence ("choose more specific codes")
    if (res.status === 422) {
      const message = tooBroadMessage(await res.json().catch(() => null));
      if (message) throw new DemandError(422, message);
    }
    throw new DemandError(res.status, DEMAND_FAILED);
  }
  return (await res.json()) as T;
}

/** The API's sentence for a request that matches too many notices (`detail: {code: 'too_broad', message}`), else null. */
export function tooBroadMessage(body: unknown): string | null {
  const d = (body as { detail?: { code?: unknown; message?: unknown } } | null)?.detail;
  return d && d.code === 'too_broad' && typeof d.message === 'string' ? d.message : null;
}
