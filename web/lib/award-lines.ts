import { formatChangeValue } from './change-format';
import { formatDateUtc, formatMoney } from './format';
import type { FieldChange, Tender, TenderVersion } from './types';

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

/**
 * The figure an award states that is set aside as implausible, said and not used; null when none. WP-103 (220199-2026): over a
 * hundred times the notice's own estimate (no `setAsideReason`). WP-108: `lots`, over a hundred times or exactly a thousand
 * times the sum of its own lot or tender values (FASER 394720-2025: that sum stands); `procedure`, the same against the value
 * another notice of its procedure states (Imprensa Nacional Casa da Moeda 499753-2026: the procedure's estimate stands).
 */
export function setAsideNote(v: { amount?: number; kind: string; currency: string; setAside?: number | null; setAsideReason?: string | null } | null | undefined): string | null {
  if (!v || !v.setAside) return null;
  const stated = formatMoney({ amount: v.setAside, currency: v.currency });
  const times = (other: number | undefined) => (other && Math.abs(v.setAside! / 1000 - other) < 0.01 ? 'exactly a thousand times' : 'over a hundred times');
  const unused = 'most likely an entry in the wrong unit, so it is in no sum or ranking';
  if (v.setAsideReason === 'lots') return `The notice states ${stated}, ${times(v.amount)} the sum of its own lot values: ${unused}; this is that sum`;
  if (v.setAsideReason === 'procedure') {
    if (v.kind !== 'estimate') return null;
    return `The award states ${stated}, ${times(v.amount)} the value the procedure’s own notice states: ${unused}; this is the procedure’s estimate`;
  }
  if (v.kind !== 'estimate') return null;
  return `The award states ${stated}, over a hundred times the buyer’s estimate: ${unused}; this is the buyer’s estimate`;
}

/**
 * WP-108 (p10: "2 corrections (below)" with nothing below): each correction by DefenceGate in one line, said in the open under
 * the version history: "Corrected 15 Oct 2026: Estimated value EUR 45,980 to EUR 38,000; Published 28 Sep 2026 to 3 Sep 2026".
 */
export function correctionLines(versions: Pick<TenderVersion, 'detectedAt' | 'changes'>[]): string[] {
  return versions.filter((v) => v.changes.length > 0).map((v) => `Corrected ${formatDateUtc(v.detectedAt)}: ${changeWords(v.changes)}`);
}

/** "Estimated value EUR 45,980 to EUR 38,000; Published 28 Sep 2026 to 3 Sep 2026". */
export function changeWords(changes: FieldChange[]): string {
  return changes.map((c) => {
    const before = formatChangeValue(c.field, c.before), after = formatChangeValue(c.field, c.after);
    if (before && after) return `${c.label} ${before} to ${after}`;
    return after ? `${c.label} ${after} added` : `${c.label}${before ? ` ${before}` : ''} removed`;
  }).join('; ');
}

/** What a correction by DefenceGate is: our corrected reading of a notice we held. */
export const CORRECTION_NOTE = 'We read the notice we already held again with a corrected reading: the publisher did not change it on this date, and it is not counted as a change.';

/**
 * WP-108 (p10: "Published changed from 28 Sep 2026 to 3 Sep 2026" read as the buyer back-dating the notice): the publication
 * date the source moved in the version that made the notice awarded (`TenderVersion.redated`), said apart; null when none.
 */
export function redatedLine(v: Pick<TenderVersion, 'redated'>): string | null {
  return v.redated && v.redated.length > 0
    ? `The source dated the notice again when it published the award (${changeWords(v.redated)}): not a change by the buyer, and not counted as one.`
    : null;
}

/** The versions listed, and DefenceGate's own corrections (remapped re-reads) apart: "3 versions observed" stood over one. */
export function versionCountLine(own: number, corrections: number): string {
  const head = own > 1 ? `${own} versions observed` : 'One version observed so far';
  return corrections > 0 ? `${head}, and ${corrections} ${corrections === 1 ? 'correction' : 'corrections'} by DefenceGate (below).` : `${head}.`;
}
