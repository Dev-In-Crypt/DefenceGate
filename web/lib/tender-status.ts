import type { StatusKind, Tender } from './types';
import { getTenderDeadline, now } from './deadline';

/**
 * What the two stamps of a tender's source badge mean. `retrievedAt` is the newest version that is not one of our own
 * re-readings of the same payload, `checkedAt` the end of the newest collection run of that source.
 */
export const TENDER_CHANGED_LABEL = 'Last change seen at the source';
export const TENDER_CHECKED_LABEL = 'Source last collected';

/** What a tender's status reads as. `word` is the plain one for exports ("Open" even when closing soon). */
export interface TenderStatusView { kind: StatusKind; label: string; word: string }

type StatusInput = Pick<Tender, 'status' | 'deadline'> & Partial<Pick<Tender, 'statusNative' | 'deadlineIsDate'>>;

/**
 * The words of the API's effective status (`statusNative`): open, expired, awarded, cancelled, forthcoming,
 * unknown. "Open" is shown only for a notice that is effectively open: an unexpected value is never read as open.
 * A server that does not send `statusNative` falls back to `status` and the deadline.
 */
export function tenderStatusView(t: StatusInput, ref: Date = now()): TenderStatusView {
  const native = (t.statusNative ?? '').trim().toLowerCase();
  const fixed = (kind: StatusKind, label: string): TenderStatusView => ({ kind, label, word: label });
  switch (native) {
    case 'awarded': return fixed('closed', 'Awarded');
    case 'cancelled': case 'canceled': return fixed('closed', 'Cancelled');
    case 'expired': return fixed('closed', 'Closed');
    case 'forthcoming': return fixed('upcoming', 'Planned');
    case 'unknown': return fixed('unknown', 'Status unknown');
    case '': case 'open': {
      if (t.status === 'closed') return fixed('closed', 'Closed');
      const d = getTenderDeadline(t, ref);
      if (d.state === 'closed') return fixed('closed', 'Closed');
      if (d.state === 'soon' || d.state === 'urgent') return { kind: 'soon', label: 'Closing soon', word: 'Open' };
      return fixed('open', 'Open');
    }
    default:
      return t.status === 'closed' ? fixed('closed', 'Closed') : fixed('unknown', 'Status unknown');
  }
}

/** The API's anomaly code for a stated deadline more than three years ahead. */
export const LONG_RUNNING = 'deadline-more-than-3y';

const ANOMALY_TEXT: Record<string, string> = {
  'deadline-before-publication': 'Deadline is before publication in the source; verify at the source.',
  [LONG_RUNNING]: 'Long-running notice: the source states a deadline more than 3 years ahead. That is usually a framework agreement or a dynamic purchasing system that stays open, not a closing date.',
};

/** A notice whose stated deadline is more than three years ahead: shown as open until then, never as "closing". */
export function isLongRunning(t: Pick<Tender, 'anomalies'>): boolean {
  return Array.isArray(t.anomalies) && t.anomalies.includes(LONG_RUNNING);
}

/** Plain-language notes for the anomaly codes we know. Unknown or missing codes give nothing. */
export function anomalyNotes(t: Pick<Tender, 'anomalies'>): string[] {
  const codes = Array.isArray(t.anomalies) ? t.anomalies : [];
  return [...new Set(codes)].map((c) => ANOMALY_TEXT[c]).filter((s): s is string => Boolean(s));
}

/**
 * The status word the source itself gives, when it gives one. `statusNative` is the API's effective status: "open"
 * and "expired" are read from the deadline (ours, not the source's), so they are not shown as "at the source".
 * Awarded, cancelled and planned are read from the type of notice the source published (TED) or its own status.
 */
export function sourceStatusWord(t: Pick<Tender, 'statusNative'>): string | null {
  switch ((t.statusNative ?? '').trim().toLowerCase()) {
    case 'awarded': return 'Awarded';
    case 'cancelled': case 'canceled': return 'Cancelled';
    case 'forthcoming': return 'Planned';
    default: return null;
  }
}

/** "Estimated value" qualifiers the API may send, as words. Anything else is shown as sent. */
export function valueKindLabel(kind: string | null | undefined): string | null {
  const k = (kind ?? '').trim();
  return k ? k.replace(/[_-]+/g, ' ') : null;
}
