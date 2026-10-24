/**
 * The site search (WP-86): one query over the five lists, GET /v1/search (backend/dgate/search.py). Each group is the
 * list endpoint's own answer for the same words, so a group's total is what its "see all" link opens. Without the API
 * (a demo build) the groups are the demo lists' own answers.
 */
import { httpOrThrow } from './api';
import * as callsMock from './mock/calls';
import * as networksMock from './mock/networks';
import * as supplierMock from './mock/suppliers';
import * as tenderMock from './mock/tenders';
import { DEFENCE_PROGRAMMES } from './networks';
import type { OrgListItem } from './networks-types';
import type { Buyer, Call, SupplierItem, Tender } from './types';
import { buyerNames, foldWords } from './search-terms';

const API_BASE = process.env.DG_API_URL;
export const SEARCH_LIMIT = 5;
export const SEARCH_MIN = 2;
export const SEARCH_MAX = 100;

export interface SearchGroup<T> {
  total: number | null;
  /** The list's total is a floor ("at least"). */
  atLeast: boolean;
  items: T[];
  /** `slow`: not answered within the search's time budget; `refused`: the list refused the words. */
  error: 'slow' | 'refused' | null;
}
export interface SiteSearch {
  q: string;
  tenders: SearchGroup<Tender>;
  funding: SearchGroup<Call>;
  buyers: SearchGroup<Buyer>;
  suppliers: SearchGroup<SupplierItem>;
  organisations: SearchGroup<OrgListItem>;
  /** WP-98: the tender part's terms of other languages and their product groups (lib/search-terms.ts). */
  alsoSearched?: string[];
  searchGroups?: { id: string; label: string; cpv: string[] }[];
  /** WP-98: the first buyer is the one the words name (an abbreviation's family, or the name itself). */
  buyerNamed?: boolean;
}

/** The words as the search takes them: trimmed, at most 100 characters, nothing when shorter than two. */
export function searchQuery(raw: string | string[] | undefined): string {
  const v = (Array.isArray(raw) ? raw[0] : raw) ?? '';
  const q = v.replace(/\s+/g, ' ').trim().slice(0, SEARCH_MAX);
  return q.length >= SEARCH_MIN ? q : '';
}

/** Where each group's "see all" leads: the list itself, searched for the same words. */
export function seeAllHref(group: keyof Omit<SiteSearch, 'q' | 'alsoSearched' | 'searchGroups' | 'buyerNamed'>, q: string): string {
  const path = { tenders: '/tenders', funding: '/funding', buyers: '/buyers', suppliers: '/suppliers', organisations: '/organisations' }[group];
  return `${path}?${new URLSearchParams({ q })}`;
}

const group = <T>(p: { items: T[]; total: number; totalCapped?: boolean; totalExact?: boolean }): SearchGroup<T> =>
  ({ total: p.total, atLeast: Boolean(p.totalCapped) || p.totalExact === false, items: p.items.slice(0, SEARCH_LIMIT), error: null });

export async function getSearch(q: string): Promise<SiteSearch> {
  if (API_BASE) {
    // Shaped by the visitor: never cached, charged to the visitor (lib/api.ts visitorHeaders).
    return httpOrThrow<SiteSearch>(`/v1/search?${new URLSearchParams({ q, limit: String(SEARCH_LIMIT) })}`, 'no-store');
  }
  const tenders = tenderMock.queryTenders({ q, pageSize: SEARCH_LIMIT });
  const buyers = group(tenderMock.queryBuyers({ q, pageSize: SEARCH_LIMIT }));
  const first = buyers.items[0];
  const buyerNamed = Boolean(first) && (buyerNames(q).length > 0 || foldWords(first.name).join('') === foldWords(q).join(''));
  return {
    q,
    alsoSearched: tenders.alsoSearched, searchGroups: tenders.searchGroups, buyerNamed,
    tenders: group(tenders),
    funding: group(callsMock.queryCalls({ q, pageSize: SEARCH_LIMIT })),
    buyers,
    suppliers: group(supplierMock.querySuppliers({ q, pageSize: SEARCH_LIMIT })),
    organisations: group(networksMock.queryOrgs({ q, programme: DEFENCE_PROGRAMMES, pageSize: SEARCH_LIMIT })),
  };
}
