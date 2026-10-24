/**
 * The demand map of the supplier report (WP-66): who in defence buys what the company makes, from the CPV codes of the supplier page.
 * The one call: `POST /api/readiness/demand` with the codes, the seven countries and (WP-105) the company’s own country, and nothing else of the profile. The server keeps
 * nothing. Pure except `fetchDemand`.
 */
import type { Profile } from './profile';
import { formatMoney } from './format';
import { AUTOMOTIVE_SET, cpvPrefix } from './cpv';
import { fetchPatiently } from './answer-cache';
import type { ValueSum, ValueTotals } from './value-totals';

/** WP-105: Portugal and Italy too (from TED; we read no national portal of theirs). */
export const DEMAND_COUNTRIES = ['ES', 'DE', 'FR', 'PL', 'NL', 'PT', 'IT'] as const;

/** `home` (WP-105): the company's own country when it is one of the map's, so its own winners are named past the first 30. */
export interface DemandRequest { cpv: string[]; countries: string[]; home?: string }

export interface DemandRef {
  id: string; slug: string; noticeId: string; title: string; buyerName: string | null; publishedAt: string | null;
  source: string; sourceUrl: string | null; directive: boolean;
}
export interface DemandBuyer {
  slug: string; name: string; core: boolean; procurements: number;
  /** WP-97: the contract values it awarded under the codes, per currency (contract values only; absent from an older answer). */
  awardedValue?: ValueSum[];
}
/** WP-97: the open tenders under the codes in one country, as /tenders counts them, and the link to that list. */
export interface OpenNow { count: number; atLeast: boolean; href: string }
export interface DemandWinner { name: string; country: string; awards: number; notices: DemandRef[] }
export interface DemandCounts { procurements: number; directive: number; coreBuyers: number; otherBuyers: number; awarded: number; winners: number }
export interface DemandCountry extends DemandCounts {
  country: string; topBuyers: DemandBuyer[]; topWinners: DemandWinner[]; otherWinners: { winners: number; awards: number }; latest: DemandRef[];
  openNow?: OpenNow | null;
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
  /** WP-97: a dealer of parts, tyres or hardware by its name (Recambios, Neumáticos, Ferretería): a competitor or distributor, not a customer. */
  distributor?: boolean;
  edfProjects: number; defenceBuyer: boolean;
  /**
   * WP-112 (p01, p02: O-rings of a pipeline notice and a vehicle maker's lot of a 23-code supply contract under the company's codes): every
   * contract of it matched only by an additional code of its notice, or by a catch-all notice of more than 20 codes; absent before.
   */
  byOtherCodeOnly?: boolean;
}
export interface Approach {
  winners: ApproachWinner[];
  /** Winners with fewer than kMin procurements: counted, never named (WP-81: kMin is 1, so none; an older answer had kMin 3). */
  below: { winners: number; awards: number };
  /** Winners with kMin or more past the first 30 (a prime is never among them). */
  more: { winners: number; awards: number };
  /** WP-105: curated primes that won none of these procurements but other defence contracts from the same buyers (absent from an older answer). */
  primesAtBuyers?: PrimeAtBuyers[];
}
export interface PrimeAtBuyers {
  name: string; slug: string; country: string | null; contracts: number;
  prime: { group: string; jointVenture: boolean; source: string; sourceUrl: string };
}
export interface Demand {
  since: string; until: string; kMin: number; countries: string[];
  codes: { code: string; prefix: string; procurements: number }[];
  total: DemandCounts; byCountry: DemandCountry[]; approach: Approach;
  coverage: string; winnersFrom: string; notice: string;
  sources: { code: string; name: string; attribution: string; lastUpdated?: string | null }[];
}

/**
 * The request for a profile: its CPV codes (at most 15, as the supplier page keeps them), the map's countries and (WP-105) the company's
 * own country when it is one of them; null without codes.
 */
export function demandRequest(p: Profile): DemandRequest | null {
  const cpv = p.supplier.cpv.filter((c) => /^\d{8}$/.test(c)).slice(0, 15);
  if (!cpv.length) return null;
  const home = (DEMAND_COUNTRIES as readonly string[]).includes(p.country) ? p.country : undefined;
  return home ? { cpv, countries: [...DEMAND_COUNTRIES], home } : { cpv, countries: [...DEMAND_COUNTRIES] };
}

/**
 * WP-68: the codes of the sample on /readiness/spain-automotive. WP-105 (p01: the landing counted 482 winners, the report 256): the codes of
 * the supplier profile's automotive button, so the landing and the report count the same codes. The page shows the API's live answer, or nothing.
 */
export const SAMPLE_CPV = AUTOMOTIVE_SET;

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
    // WP-105 (p01, p04): "the report names them all under Who to approach" was not so (that list stops too); the list of every winner does
    : `${head} not listed here: the list shows the ten with the most awards per country; every one of them is on the list of all winners for these codes.`;
}

/** The winners not named in "who to approach", in words: the mosaic rule, and the end of the list. */
export function approachOthersLine(a: Approach, kMin: number): string | null {
  const n = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;
  const parts: string[] = [];
  if (a.below.winners > 0) {
    parts.push(`${n(a.below.winners, 'other winner', 'other winners')} with fewer than ${kMin} awards each (${n(a.below.awards, 'award', 'awards')} together) ` +
      `${a.below.winners === 1 ? 'is' : 'are'} counted, not named.`);
  }
  if (a.more.winners > 0 && kMin <= 1) {
    // WP-105 (p01: "37 are named below" then "the list stops at 30"): the list is the 30 with the most contracts, every prime and the
    // company's own country's winners, so it can be longer than 30
    parts.push(`${n(a.more.winners, 'more winner', 'more winners')} (${n(a.more.awards, 'award', 'awards')}) ${a.more.winners === 1 ? 'is' : 'are'} not ` +
      'listed here: the list names the 30 with the most contracts, every prime contractor or large defence group, and the winners of your own ' +
      'country; every winner is on the list of all winners for these codes.');
  } else if (a.more.winners > 0) {
    parts.push(`${n(a.more.winners, 'more winner', 'more winners')} with ${kMin} or more awards (${n(a.more.awards, 'award', 'awards')}) ` +
      `${a.more.winners === 1 ? 'is' : 'are'} not listed: the list stops at 30, and every prime contractor or large defence group is on it.`);
  }
  return parts.length ? parts.join(' ') : null;
}

/**
 * WP-87: the sample's sentence about the winners, in the numbers the report and its winners page use. Since WP-81 every legal entity is
 * named: "who to approach" lists the most contracts first (and every prime), the winners page all of them ("41 companies would be
 * named" was the list's length, read as all that is named; and the two words ran together).
 */
export function approachSentence(d: Pick<Demand, 'total' | 'approach' | 'kMin'>): string {
  const n = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;
  const all = d.total.winners;
  const listed = d.approach.winners.length;
  const primes = d.approach.winners.filter((w) => w.prime).length;
  const named = d.kMin > 1 ? all - d.approach.below.winners : all;
  return `${n(all, 'company', 'companies')} won them. The report names ${named === all ? (all === 1 ? 'it' : 'every one of them') : `the ${named} with ${d.kMin} or more contracts`}: `
    + `${listed === named ? 'all of them' : `the ${listed} with the most contracts, and every prime contractor or large defence group,`} under “who to approach”`
    + `${listed === named ? '' : `, and all ${named} on its list of winners`}. ${n(primes, 'of those listed is', 'of those listed are')} marked as a prime contractor or large defence group.`;
}

/** WP-112: whether the winner at `i` is the first of its prime group in the list (its source line is shown there only). */
export function firstOfGroup(ws: readonly ApproachWinner[], i: number): boolean {
  const g = ws[i]?.prime?.group;
  return !g || ws.findIndex((w) => w.prime?.group === g) === i;
}

/** The primes and large defence groups among the named winners, the realistic way in for a subcontractor. */
export function primesOf(a: Approach): ApproachWinner[] {
  return a.winners.filter((w) => w.prime !== null);
}

/**
 * WP-89 (UX audit, section 4): the named winners in three groups, each most contracts first (the answer's order): the direct suppliers of
 * the company's own country (Suyfa, JPG, MADZEAL for a Spanish one), the primes and large defence groups (those of its country first), and
 * the other winners. A Spanish user saw eight German primes before any Spanish winner.
 */
export function approachGroups(a: Approach, country: string): { home: ApproachWinner[]; primes: ApproachWinner[]; others: ApproachWinner[]; dealers: ApproachWinner[]; side: ApproachWinner[] } {
  // WP-112: a winner matched only by an additional code of its notices is listed apart, last, prime or not
  const main = a.winners.filter((w) => !w.byOtherCodeOnly);
  const primes = main.filter((w) => w.prime !== null);
  // WP-97: the dealers of parts, tyres and hardware apart, own country first: competitors or distributors of a maker, not its customers
  const plain = main.filter((w) => !w.prime && !w.distributor);
  const dealers = main.filter((w) => !w.prime && w.distributor);
  return {
    home: plain.filter((w) => w.country === country),
    primes: ownFirst(primes, country),
    others: plain.filter((w) => w.country !== country),
    dealers: ownFirst(dealers, country),
    side: ownFirst(a.winners.filter((w) => w.byOtherCodeOnly), country),
  };
}

/** WP-97: the company's own country first, the order of the rest kept (who buys, who wins, the sections of the report). */
export function ownFirst<T extends { country: string | null }>(xs: readonly T[], country: string): T[] {
  return [...xs.filter((x) => x.country === country), ...xs.filter((x) => x.country !== country)];
}

/** WP-97: "EUR 1,200,000 over 3 contracts; PLN 40,000 over 1 contract", the contract values a buyer awarded under the codes; null for none. */
export function buyerAmount(b: DemandBuyer): string | null {
  const xs = b.awardedValue ?? [];
  if (xs.length === 0) return null;
  return xs.map((s) => `${formatMoney({ currency: s.currency, amount: Math.round(s.amount) })} over ${s.count} ${s.count === 1 ? 'contract' : 'contracts'}`).join('; ');
}

/** WP-97: the link to the open tenders under the codes in a country: the answer's own (the same count), else built from the codes' prefixes. */
export function openHref(d: Pick<Demand, 'codes' | 'byCountry'>, country: string): string {
  const own = d.byCountry.find((c) => c.country === country)?.openNow?.href;
  if (own) return own;
  const cpv = [...new Set(d.codes.map((c) => c.prefix))].join(',');
  return `/tenders?country=${country}&cpv=${cpv}`;
}

/**
 * WP-89: a winner's supplier page with the report's codes and countries, so that the page says how many of its contracts are under them
 * (`/v1/suppliers/{slug}?cpv=&buyerCountry=`, the count "who to approach" gives).
 */
export function supplierHref(slug: string, request: DemandRequest | null): string {
  if (!request) return `/suppliers/${slug}`;
  const p = new URLSearchParams({ cpv: request.cpv.join(','), buyerCountry: request.countries.join(',') });
  return `/suppliers/${slug}?${p.toString()}`;
}

/**
 * WP-112 (p02: the army's top suppliers led by a vehicle maker on the page the report linked): a buyer's page under the report's codes, so
 * its open tenders and top suppliers are those of the company's trade. `codes`: 8-digit codes or prefixes; each is read at its level.
 */
export function buyerHref(slug: string, codes: readonly string[] = []): string {
  const prefixes = [...new Set(codes.map(cpvPrefix))];
  return `/buyers/${slug}${prefixes.length ? `?${new URLSearchParams({ cpv: prefixes.join(',') }).toString()}` : ''}`;
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
  const res = await fetchPatiently(path, {
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
