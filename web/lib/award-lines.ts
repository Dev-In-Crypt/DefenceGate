import { formatMoney } from './format';
import type { Tender } from './types';

/**
 * WP-103: three lines of a tender page, kept here so a lib check can hold them.
 *
 * The winners of an award DefenceGate has not read: a core notice not read yet, or a notice outside the core scope,
 * whose winners are not read at all (owner decision of 22 October 2026: the TED award load reads the core scope).
 * null when the page names winners, the notice is no award, or the API does not say (an older build).
 */
export function winnersNotReadLine(t: Pick<Tender, 'statusNative' | 'scope' | 'winnersRead' | 'awardedTo' | 'awardedPersons'>): string | null {
  if (t.winnersRead !== false || t.statusNative !== 'awarded') return null;
  if ((t.awardedTo ?? []).length > 0 || (t.awardedPersons ?? 0) > 0) return null;
  return t.scope === 'core'
    ? 'not read yet by DefenceGate; the original notice names the winners'
    : 'not read by DefenceGate: winners are read for the notices of the defence core scope, and this notice is listed for its buyer only; the original notice names them';
}

/** The figure an award states that its own estimate contradicts, said and not used (220199-2026); null when none. */
export function setAsideNote(v: { kind: string; currency: string; setAside?: number | null } | null | undefined): string | null {
  if (!v || v.kind !== 'estimate' || !v.setAside) return null;
  return `The award states ${formatMoney({ amount: v.setAside, currency: v.currency })}, over a hundred times the buyer’s estimate: most likely an entry in the wrong unit, so it is in no sum or ranking; this is the buyer’s estimate`;
}

/** The versions listed, and DefenceGate's own corrections (remapped re-reads) apart: "3 versions observed" stood over one. */
export function versionCountLine(own: number, corrections: number): string {
  const head = own > 1 ? `${own} versions observed` : 'One version observed so far';
  return corrections > 0 ? `${head}, and ${corrections} ${corrections === 1 ? 'correction' : 'corrections'} by DefenceGate (below).` : `${head}.`;
}
