/**
 * WP-105 (persona round of 24 October 2026, p07: "no spending totals by country, CPV or buyer"): the words of the contract-value sums on the
 * market overview and the buyer pages. The API sums (backend `money.py`, `suppliers.buyer_suppliers`: contract values only, per currency,
 * never converted, framework ceilings and estimates never added); this only words them. Pure: lib/wp105.check.ts holds it.
 */
import { formatMoney, formatNumber } from './format';
import type { ValueSum } from './value-totals';

/** "EUR 1,200,000 over 3 contracts; PLN 40,000 over 1 contract", the largest count first as the API orders them; null for none. */
export function moneyLine(xs: readonly ValueSum[] | undefined | null): string | null {
  if (!xs || xs.length === 0) return null;
  return xs.map((s) => `${formatMoney({ currency: s.currency, amount: Math.round(s.amount) })} over ${formatNumber(s.count)} ${s.count === 1 ? 'contract' : 'contracts'}`).join('; ');
}

/** "18 of 25 state a contract value", the coverage of a sum. */
export function valuedShare(of: number, withoutValue: number): string {
  const valued = Math.max(0, of - withoutValue);
  return `${formatNumber(valued)} of ${formatNumber(of)} ${of === 1 ? 'states' : 'state'} a contract value`;
}

