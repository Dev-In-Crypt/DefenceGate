import type { Opportunity, OpportunityFilters, OpportunityVersion, Paginated } from '../types';

// Tender mock data (≈15 notices incl. NL, 2–4 versions on amended ones) lands with P2.
export const opportunities: Opportunity[] = [];
export const versions: Record<string, OpportunityVersion[]> = {};

export function queryOpportunities(f: OpportunityFilters): Paginated<Opportunity> {
  const pageSize = f.pageSize ?? 10;
  return { items: [], total: opportunities.length, page: f.page ?? 1, pageSize };
}
