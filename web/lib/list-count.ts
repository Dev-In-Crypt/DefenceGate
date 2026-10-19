/**
 * How a bounded tender list and its counts read (API contract, "Changes of 19 October 2026"): a total that stopped
 * at its cap is "at least", the list serves no position past `maxOffset`, the scope counts say when they were worked
 * out and how many notices two of them share. Pure and import-light: lib/wp52b.check.ts runs it on its own.
 */
import { formatNumber, formatTimeUtc } from './format';
import type { ScopeCounts } from './types';

interface Bounded { total: number; totalCapped?: boolean; maxOffset?: number }

/** "at least 10,000" for a count that stopped; undefined for an exact one (the heading then prints the number). */
export function totalWords(r: Pick<Bounded, 'total' | 'totalCapped'>): string | undefined {
  return r.totalCapped === true ? `at least ${formatNumber(r.total)}` : undefined;
}

/** How many results the pager can reach: the total, but never past the position the list stops serving. */
export function reachableTotal(r: Bounded): number {
  return r.maxOffset !== undefined ? Math.min(r.total, r.maxOffset) : r.total;
}

/** The list stops short of its results: there are more than it serves (an exact total above the cap, or a count that is "at least" it). */
export function listIsCut(r: Bounded): boolean {
  return r.maxOffset !== undefined && (r.total > r.maxOffset || (r.totalCapped === true && r.total >= r.maxOffset));
}

/** The sentence under a list that stops at its cap, pointing at the filters. null when the list is not cut. */
export function cutSentence(r: Bounded): string | null {
  if (!listIsCut(r) || r.maxOffset === undefined) return null;
  return `The list shows the first ${formatNumber(r.maxOffset)} tenders of this search. Narrow it with the filters (country, CPV code, deadline dates, status) to reach the others.`;
}

/** The count beside a scope choice: "(1,522)", or "(at least 1,522)" when the count stopped at its cap. */
export function scopeCountText(n: number, capped: boolean | undefined): string {
  return capped === true ? ` (at least ${formatNumber(n)})` : ` (${formatNumber(n)})`;
}

/** "Counts as of 11:05 UTC": when the scope counts were worked out; null when the API does not say. */
export function countsAsOf(asOf: string | null | undefined): string | null {
  const t = asOf ? formatTimeUtc(asOf) : '';
  return t ? `Counts as of ${t}` : null;
}

/** The two notes together, for a place that shows the three counts without a filter: "Counts as of 11:05 UTC. Core and supplies ...". null when there is neither. */
export function countsNote(c: Pick<ScopeCounts, 'asOf' | 'overlap'> | null | undefined): string | null {
  const parts = [countsAsOf(c?.asOf) ? `${countsAsOf(c?.asOf)}.` : null, overlapNote(c)].filter((s): s is string => s !== null);
  return parts.length > 0 ? parts.join(' ') : null;
}

/** Core and supplies share notices (the national copy of a core notice is listed once in the first count): said, so the three counts add up. */
export function overlapNote(c: Pick<ScopeCounts, 'overlap'> | null | undefined): string | null {
  const n = c?.overlap ?? 0;
  return n > 0 ? `Core and supplies add up to ${formatNumber(n)} more than the first count: ${formatNumber(n)} supply ${n === 1 ? 'notice is' : 'notices are'} the national copy of a core notice, which the first count shows once.` : null;
}
