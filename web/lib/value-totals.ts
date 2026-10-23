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
  /** Of them, those whose value is the sum of the lots' estimated values, not a stated total. */
  lotEstimates: number;
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
}

const n = (k: number, noun: string) => `${formatNumber(k)} ${k === 1 ? noun : `${noun}s`}`;

/** "EUR 3,000 over 2 contracts (1 of them is the sum of the lots' estimated values, not a stated total)", one line per currency. */
export function sumLines(v: ValueTotals, noun: string): string[] {
  const lots = (s: ValueSum) => {
    if (s.lotEstimates === 0) return '';
    const which = s.count === 1 ? 'it is' : s.lotEstimates === s.count ? 'all are' : `${formatNumber(s.lotEstimates)} of them ${s.lotEstimates === 1 ? 'is' : 'are'}`;
    return ` (${which} the sum of the lots’ estimated values, not a stated total)`;
  };
  return v.byCurrency.map((s) => `${formatMoney({ currency: s.currency, amount: Math.round(s.amount) })} over ${n(s.count, noun)}${lots(s)}`);
}

/** "12 of 30 contracts state no value for this company alone; 4 of them name several winners." Null when every one states one. */
export function withoutValueLine(v: ValueTotals, noun: string): string | null {
  if (v.withoutValue === 0) return null;
  const head = `${formatNumber(v.withoutValue)} of ${n(v.of, noun)} ${v.withoutValue === 1 ? 'states' : 'state'} no value for this company alone`;
  if (v.shared === 0) return `${head}.`;
  return `${head}; ${v.shared === v.withoutValue ? (v.shared === 1 ? 'it names' : 'they name') : `${formatNumber(v.shared)} of them ${v.shared === 1 ? 'names' : 'name'}`} several winners.`;
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
  + 'PLACSP values are the awarded amounts; TED values are as the notice states them. Each contract is counted once, however many notices '
  + 'publish it: where TED and PLACSP both do, PLACSP’s awarded amount, else TED’s value. Values as published by the buyer; some may be '
  + 'framework ceilings.';
