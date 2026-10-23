/**
 * WP-81 (owner decision of 22 October 2026): the sum of the values of one supplier's contracts, per currency, in the words of the
 * collapsed "Contract values" block of the supplier page and of "who to approach". The API sums (backend `suppliers.value_totals`);
 * this only words it. Pure.
 */
import { formatMoney, formatNumber } from './format';

export interface ValueSum {
  currency: string; amount: number;
  /** The contracts (or notices) whose value this is. */
  count: number;
  /** WP-95: always 0 (a sum of lot estimates is an estimate, in `estimates`); kept for older APIs. */
  lotEstimates: number;
}
/** WP-95: one of the largest contract values, with its notice. */
export interface LargestContract {
  id: string; slug: string; noticeId: string; title: string; buyerName: string | null; publishedAt: string | null;
  amount: number; currency: string; sourceUrl: string | null; source: string;
}
/** GET /v1/suppliers/{slug} `values`, and each winner's `values` in POST /v1/readiness/demand `approach`. */
export interface ValueTotals {
  byCurrency: ValueSum[];
  /** The contracts behind the sums: every one of the list's. */
  of: number;
  /** Of them, those with no value that is this winner's. */
  withoutValue: number;
  /** Of those, the ones naming several winners. */
  shared: number;
  /** WP-87: contracts whose value is under 1,000, probably a unit price: in no sum. Absent from older APIs. */
  suspect?: number;
  /** WP-95: framework ceilings and estimates, never added to the contract values. Absent from older APIs. */
  frameworks?: ValueSum[];
  estimates?: ValueSum[];
  /** WP-95: the largest contract values (at most 10), with their notices. */
  largest?: LargestContract[];
}

/** WP-95: the words for what an amount is, on rows and labels. */
export const VALUE_KIND_LABEL = { contract: 'contract value', framework: 'framework ceiling', estimate: 'estimate' } as const;

/** WP-95: "Framework ceilings, not added: EUR 1,250,000 (1 framework)", one line per kind that has any. */
export function apartLines(v: ValueTotals): string[] {
  const line = (sums: ValueSum[] | undefined, head: string, noun: string) => (sums && sums.length > 0
    ? [`${head}: ${sums.map((s) => `${formatMoney({ currency: s.currency, amount: Math.round(s.amount) })} (${n(s.count, noun)})`).join('; ')}`]
    : []);
  return [...line(v.frameworks, 'Framework ceilings, not added to the contract values', 'framework'),
    ...line(v.estimates, 'Estimates where the award states no value, not added', 'notice')];
}

const n = (k: number, noun: string) => `${formatNumber(k)} ${k === 1 ? noun : `${noun}s`}`;

/** "EUR 3,000 over 2 contracts", one line per currency (WP-95: contract values only; a lot estimate is an estimate now). */
export function sumLines(v: ValueTotals, noun: string): string[] {
  return v.byCurrency.map((s) => `${formatMoney({ currency: s.currency, amount: Math.round(s.amount) })} over ${n(s.count, noun)}`);
}

/** "12 of 30 contracts state no value for this company alone; 4 of them name several winners." Null when every one states one. */
export function withoutValueLine(v: ValueTotals, noun: string): string | null {
  if (v.withoutValue === 0) return null;
  const head = `${formatNumber(v.withoutValue)} of ${n(v.of, noun)} ${v.withoutValue === 1 ? 'states' : 'state'} no value for this company alone`;
  if (v.shared === 0) return `${head}.`;
  return `${head}; ${v.shared === v.withoutValue ? (v.shared === 1 ? 'it names' : 'they name') : `${formatNumber(v.shared)} of them ${v.shared === 1 ? 'names' : 'name'}`} several winners.`;
}

/**
 * WP-89: the summary line of the collapsed block: the sums, one per currency ("EUR 1,200,000 over 3 contracts; PLN 40,000 over 1
 * contract"), or "no stated value" when there is none to sum. The details (what states no value, the unit prices) stay inside.
 */
export function totalLine(v: ValueTotals, noun: string): string {
  if (v.byCurrency.length === 0) return (v.frameworks?.length || v.estimates?.length) ? 'no contract value; ceilings or estimates only' : 'no stated value';
  const sums = v.byCurrency.map((s) => `${formatMoney({ currency: s.currency, amount: Math.round(s.amount) })} over ${n(s.count, noun)}`).join('; ');
  // the sum is not the company's whole: say how many state no value of their own (the line is all that prints)
  return v.withoutValue > 0 ? `${sums}; ${formatNumber(v.withoutValue)} of ${n(v.of, noun)} state none` : sums;
}

/** WP-87: the value under which a contract's figure is read as a unit price (the API's SUPPLIERS.SUSPECT_VALUE_MAX). */
export const SUSPECT_VALUE_MAX = 1000;
/** The cell of a contract whose value is under SUSPECT_VALUE_MAX. */
export const SUSPECT_NOTE = 'value as published, probably a unit price';

/** "2 contracts state a value under 1,000 (probably a unit price) and are left out of the sums." Null when none does. */
export function suspectLine(v: ValueTotals, noun: string): string | null {
  const k = v.suspect ?? 0;
  if (k === 0) return null;
  return `${n(k, noun)} ${k === 1 ? 'states' : 'state'} a value under ${formatNumber(SUSPECT_VALUE_MAX)} (probably a unit price, not the ${noun}’s value) and ${k === 1 ? 'is' : 'are'} left out of the sums.`;
}

/** The rules of the sum, the same wherever it is shown. */
export const VALUE_RULES = 'Summed per currency, never converted; amounts without VAT where the source states both. A value counts only where a '
  + 'notice (in Spain’s national portal, PLACSP, a lot) names this one winner: a value shared by several winners is given to none of them. '
  + 'Only contract values are summed: the ceiling of a framework agreement or dynamic purchasing system, and an estimate where the award states '
  + 'no value, are listed apart and never added, so a framework is never counted with its call-offs. PLACSP values are the awarded amounts; TED '
  + 'values are what the award notice states. Each contract is counted once, however many notices publish it: where TED and PLACSP both do, a '
  + 'contract value before a ceiling, PLACSP’s awarded amount before TED’s.';
