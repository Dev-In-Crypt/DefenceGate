import type { StatusKind, Tender } from './types';
import { getTenderDeadline, now } from './deadline';

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

const ANOMALY_TEXT: Record<string, string> = {
  'deadline-before-publication': 'Deadline is before publication in the source; verify at the source.',
  'deadline-more-than-3y': 'Deadline is more than 3 years ahead in the source.',
  'deadline-more-than-1y': 'Deadline is more than a year ahead in the source; verify it at the source.',
  'deadline-differs-from-ted-twin': 'The national notice gives another deadline; the one shown is the TED notice's.',
};

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
