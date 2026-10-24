import type { StatusKind, Tender } from './types';
import { getTenderDeadline, now } from './deadline';

/**
 * What the two stamps of a tender's source badge mean. `retrievedAt` is the newest version that is not one of our own
 * re-readings of the same payload, `checkedAt` the end of the newest collection run of that source.
 */
export const TENDER_CHANGED_LABEL = 'Last change seen at the source';
/** For a notice with no change seen: `retrievedAt` is the time we first collected it, not something the source did. */
export const TENDER_FIRST_SEEN_LABEL = 'First seen by us';
export const TENDER_CHECKED_LABEL = 'Source last collected';

/**
 * What the first stamp of a tender's source badge is. "Last change seen at the source" only when the API says the stamp
 * is an amendment (`lastChangeKind`); otherwise it is when we first collected the notice, which is what 65 % of the
 * pages showed under the old label (UX audit T11). An API build that does not send the kind gets the careful label.
 */
export function tenderChangedLabel(source: Pick<Tender['source'], 'lastChangeKind'>): string {
  return source.lastChangeKind === 'amendment' ? TENDER_CHANGED_LABEL : TENDER_FIRST_SEEN_LABEL;
}

/** What a tender's status reads as. `word` is the plain one for exports ("Open" even when closing soon). */
export interface TenderStatusView { kind: StatusKind; label: string; word: string }

type StatusInput = Pick<Tender, 'status' | 'deadline'> & Partial<Pick<Tender, 'statusNative' | 'deadlineIsDate' | 'anomalies' | 'title' | 'procedure'>>;

/** The API's anomaly code (WP-87): the TED notice's first deadline has passed, the notice's own (later) one has not. */
export const FIRST_DEADLINE_PASSED = 'first-deadline-passed';
const DPS = /dynamic purchasing|sistema din[aá]mico|syst[eè]me d.acquisition dynamique|dynamiczn\w* system|dynamisch\w* beschaffungssystem|dynamisch aankoopsysteem/i;

/** "Open (dynamic purchasing system): first deadline passed", or "Open: first deadline passed" when the notice does not say it is one. */
export function firstDeadlineLabel(t: Partial<Pick<Tender, 'title' | 'procedure'>>): string {
  return DPS.test(`${t.title ?? ''} ${t.procedure ?? ''}`) ? 'Open (dynamic purchasing system): first deadline passed' : 'Open: first deadline passed';
}

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
      // WP-87: open by the notice's own deadline while TED's first round has closed: never a "Closed" card on the Open list
      if (Array.isArray(t.anomalies) && t.anomalies.includes(FIRST_DEADLINE_PASSED)) return { kind: 'open', label: firstDeadlineLabel(t), word: 'Open' };
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
  'deadline-more-than-1y': 'Deadline is more than a year ahead in the source; verify it at the source.',
  'deadline-differs-from-ted-twin': "The national notice gives another deadline; the one shown is the TED notice's.",
  [FIRST_DEADLINE_PASSED]: 'The deadline in the TED notice (the first round) has passed; this notice states a later one and is open until then. That is how a dynamic purchasing system or a framework that takes new requests reads; check the source.',
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

/** WP-95: the label of an award's value by its kind. WP-106: the list cards and the CSV use the same words. */
export const AWARD_VALUE_LABEL = { contract: 'Awarded value', framework: 'Framework ceiling', estimate: 'Estimated value' } as const;

/** WP-106: "Madzeal, S.L.; Indra Sistemas S.A. and 3 more", and the persons counted, never named; null with nobody named. */
export function winnersLine(t: Pick<Tender, 'awardedTo' | 'awardedPersons'>, shown = 2, name: (s: string) => string = (s) => s): string | null {
  const names = (t.awardedTo ?? []).map((w) => name(w.name));
  const persons = t.awardedPersons ?? 0;
  if (names.length === 0 && persons === 0) return null;
  const rest = names.length - shown;
  const head = names.slice(0, shown).join('; ') + (rest > 0 ? ` and ${rest} more` : '');
  const people = persons > 0 ? `${persons === 1 ? 'a natural person' : `${persons} natural persons`}, not named` : '';
  return [head, people].filter(Boolean).join(names.length > 0 && people ? '; and ' : '');
}

const folded = (s: string) => s.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();

/** WP-106: the subject when it says more than the title (a card does not repeat the title under it); null otherwise. */
export function subjectAddsTo(subject: string | null | undefined, title: string | null | undefined): string | null {
  const s = (subject ?? '').trim();
  if (!s) return null;
  const a = folded(s), b = folded(title ?? '');
  return a && !b.includes(a) ? s : null;
}

/** "Estimated value" qualifiers the API may send, as words. Anything else is shown as sent. */
export function valueKindLabel(kind: string | null | undefined): string | null {
  const k = (kind ?? '').trim();
  return k ? k.replace(/[_-]+/g, ' ') : null;
}
