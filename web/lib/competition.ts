/**
 * WP-152: the words and numbers of a company's competitor intelligence (GET /v1/suppliers/{slug}/competition, backend/dgate/competition.py).
 * Pure, import-free but for formatting, so lib/wp152.check.ts runs it on its own.
 */
import { formatNumber } from './format';
import type { CompetitionShare, SupplierCompetition } from './types';

/** "12%", "4.3%", "under 0.1%": a share of a few per cent keeps one decimal, so 0.4% is not printed as 0%. */
export function sharePercent(part: number, whole: number): string {
  if (!whole) return '';
  const p = (part / whole) * 100;
  if (p > 0 && p < 0.1) return 'under 0.1%';
  return `${p >= 10 ? Math.round(p) : Math.round(p * 10) / 10}%`;
}

/** "2 of 40 contracts (5%)" */
export function countShare(s: CompetitionShare): string {
  return `${formatNumber(s.contracts)} of ${formatNumber(s.total)} (${sharePercent(s.contracts, s.total)})`;
}

/** "EUR 1,000,000 of EUR 3,000,000 (33%), over 2 valued contracts", or null when the slice states no value. */
export function valueShare(s: CompetitionShare): string | null {
  if (!s.currency || s.valueTotal == null || !s.valuedTotal) return null;
  const own = s.value ?? 0;
  return `${s.currency} ${formatNumber(own)} of ${s.currency} ${formatNumber(s.valueTotal)} (${sharePercent(own, s.valueTotal)}), over ${formatNumber(s.valuedTotal)} contracts with a stated value`;
}

/** The typical stated contract value, with how many contracts state none: never a median of nothing. */
export function sizeLine(c: Pick<SupplierCompetition, 'size' | 'withoutValue' | 'contracts'>): string {
  const none = `${formatNumber(c.withoutValue)} of its ${formatNumber(c.contracts)} contracts state no contract value`;
  if (!c.size) return `No contract value stated: ${none}.`;
  const other = c.size.otherCurrencies ? `; ${formatNumber(c.size.otherCurrencies)} more in another currency` : '';
  return `Median ${c.size.currency} ${formatNumber(c.size.median)}, over the ${formatNumber(c.size.valued)} contracts with a value in ${c.size.currency}${other}. ${none}.`;
}

/**
 * A CPV class with its official title where the selection holds the class code ("3541 Armoured military vehicles"), else with the title
 * of its group, said as such ("3542 (group 354: Military vehicles and associated parts)"): a group's title is never given as the class's.
 */
export function classLabel(cls: string, title: (code: string) => string | null, group: (code: string) => string | null): string {
  const own = title(`${cls}0000`);
  if (own) return `${cls} ${own}`;
  const g = group(cls.slice(0, 3));
  return g ? `${cls} (group ${cls.slice(0, 3)}: ${g})` : cls;
}
