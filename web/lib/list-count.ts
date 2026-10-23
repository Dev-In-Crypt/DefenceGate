/**
 * How a bounded tender list and its counts read (API contract, "Changes of 19 October 2026"): a total that stopped
 * at its cap is "at least", the list serves no position past `maxOffset`, the scope counts say when they were worked
 * out and how many notices two of them share. Pure and import-light: lib/wp52b.check.ts runs it on its own.
 */
import { formatDateUtc, formatNumber, formatTimeUtc } from './format';
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

/**
 * WP-87: the stamps of a tender list page. The list and its scope counts are two answers, each kept a few minutes: when they are of
 * the same minute both say the one time ("Counts as of 11:05 UTC"); otherwise the header names the list's time and the scope box
 * its own, with why they can differ. Two bare "Counts as of" of different times was the audit's finding.
 */
export function listStamps(list: { asOf?: string | null }, scope: { asOf?: string | null } | null | undefined): { list: string | null; scope: string | null } {
  const a = list.asOf ? formatTimeUtc(list.asOf) : '';
  const b = scope?.asOf ? formatTimeUtc(scope.asOf) : '';
  if (!a) return { list: null, scope: b ? `Scope counts as of ${b}` : null };
  if (!b || a === b) return { list: `Counts as of ${a}`, scope: b ? `Counts as of ${b}` : null };
  return { list: `List as of ${a}`, scope: `Scope counts as of ${b}, worked out apart from the list (as of ${a}); notices that opened or closed in between make them differ` };
}

/**
 * The two notes together, for a place that shows the three counts without a filter (the home page, beside tiles that carry a date):
 * "Counts as of 19 Oct 2026, 11:05 UTC. Core and supplies ...". null when there is neither.
 */
export function countsNote(c: Pick<ScopeCounts, 'asOf' | 'overlap'> | null | undefined): string | null {
  const at = c?.asOf && countsAsOf(c.asOf) ? `Counts as of ${formatDateUtc(c.asOf)}, ${formatTimeUtc(c.asOf)}.` : null;
  const parts = [at, overlapNote(c)].filter((s): s is string => s !== null);
  return parts.length > 0 ? parts.join(' ') : null;
}

/** Core and supplies share notices (the national copy of a core notice is listed once in the first count): said, so the three counts add up. */
export function overlapNote(c: Pick<ScopeCounts, 'overlap'> | null | undefined): string | null {
  const n = c?.overlap ?? 0;
  return n > 0 ? `Core and supplies add up to ${formatNumber(n)} more than the first count: ${formatNumber(n)} supply ${n === 1 ? 'notice is' : 'notices are'} the national copy of a core notice, which the first count shows once.` : null;
}
