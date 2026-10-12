import type { Call, CallStatus, DeadlineState, IsoDateTime, StatusKind, Tender } from './types';
import { formatDateLabelledUtc, formatDateTimeUtc } from './format';

/** Thresholds from the design system's deadline states. */
export const SOON_DAYS = 30;
export const URGENT_DAYS = 7;
const DAY_MS = 86_400_000;

/** Reference "now". NEXT_PUBLIC_DG_NOW pins it for demos, tests and screenshots. */
export function now(): Date {
  const pinned = process.env.NEXT_PUBLIC_DG_NOW;
  return pinned ? new Date(pinned) : new Date();
}

function utcDay(d: Date): number {
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

/**
 * Calendar days between today (UTC) and the deadline day (UTC). -1 once passed.
 * null when there is no stated deadline: that is not "closed" and has no countdown.
 */
export function daysLeft(deadline: IsoDateTime | null, ref: Date = now()): number | null {
  if (deadline === null) return null;
  const d = new Date(deadline);
  if (d.getTime() <= ref.getTime()) return -1;
  return Math.round((utcDay(d) - utcDay(ref)) / DAY_MS);
}

export function deadlineState(deadline: IsoDateTime | null, ref: Date = now()): DeadlineState {
  const days = daysLeft(deadline, ref);
  if (days === null) return 'none';
  if (days < 0) return 'closed';
  if (days <= URGENT_DAYS) return 'urgent';
  if (days <= SOON_DAYS) return 'soon';
  return 'normal';
}

/** "" when there is no deadline: no countdown is shown. */
export function countdownLabel(days: number | null): string {
  if (days === null) return '';
  if (days < 0) return 'Closed';
  if (days === 0) return 'Today';
  if (days === 1) return 'in 1 day';
  return `in ${days} days`;
}

export function stateLabel(state: DeadlineState): string {
  return {
    normal: 'Deadline', soon: 'Closing soon', urgent: 'Closes this week', closed: 'Closed', none: 'No fixed deadline',
  }[state];
}

export function statusFromState(state: DeadlineState): StatusKind {
  if (state === 'closed') return 'closed';
  return state === 'normal' || state === 'none' ? 'open' : 'soon';
}

/**
 * Status pill for a call. The API's status wins: a forthcoming call is "Opens soon" whatever its
 * deadline says; "Closing soon" only refines an open call.
 */
export function callStatusKind(status: CallStatus, state: DeadlineState): StatusKind {
  if (status === 'forthcoming') return 'upcoming';
  if (status === 'closed' || state === 'closed') return 'closed';
  return state === 'soon' || state === 'urgent' ? 'soon' : 'open';
}

export interface DeadlineInfo {
  /** null when there is no stated deadline. */
  iso: IsoDateTime | null;
  /** null when there is no stated deadline. */
  days: number | null;
  state: DeadlineState;
  /** "26 Nov 2026, 16:00 UTC"; "" when there is no deadline. */
  utc: string;
  /** "in 46 days" | "Today" | "Closed"; "" when there is no deadline. */
  countdown: string;
  label: string;
  /** The source states a date, not a time of day (tenders only). */
  dateOnly?: boolean;
}

/** Single entry point for all deadline presentation. */
export function getDeadline(deadline: IsoDateTime | null, ref: Date = now()): DeadlineInfo {
  const days = daysLeft(deadline, ref);
  const state = deadlineState(deadline, ref);
  return {
    iso: deadline, days, state,
    utc: deadline === null ? '' : formatDateTimeUtc(deadline),
    countdown: countdownLabel(days),
    label: stateLabel(state),
  };
}

/** Same as getDeadline, but a call the API reports as closed is shown closed even without a date. */
export function getCallDeadline(call: Pick<Call, 'status' | 'deadline'>, ref: Date = now()): DeadlineInfo {
  const info = getDeadline(call.deadline, ref);
  if (call.status !== 'closed' || info.state === 'closed') return info;
  return { ...info, state: 'closed', countdown: 'Closed', label: stateLabel('closed') };
}

/** A planned notice, or one of unknown status, is not under time pressure: "Closing soon" is for open ones. */
const calm = (i: DeadlineInfo): DeadlineInfo =>
  i.state === 'soon' || i.state === 'urgent' ? { ...i, state: 'normal', label: stateLabel('normal') } : i;

/**
 * Deadline of a tender. A source that gives a date only (`deadlineIsDate`, or a time of exactly 00:00 UTC on an
 * API that does not say) is shown as a date: the notice stays open until the end of that UTC day. A tender the
 * API reports as closed is shown closed, except one that is planned or of unknown status: those are not
 * "closed", so their date carries no "Closed" countdown.
 */
export function getTenderDeadline(
  tender: Pick<Tender, 'status' | 'deadline'> & Partial<Pick<Tender, 'statusNative' | 'deadlineIsDate'>>,
  ref: Date = now(),
): DeadlineInfo {
  const { deadline } = tender;
  const notClosed = tender.statusNative === 'forthcoming' || tender.statusNative === 'unknown';
  if (deadline === null) return notClosed ? getDeadline(null, ref) : getCallDeadline(tender, ref);
  const d = new Date(deadline);
  const inferred = d.getUTCHours() === 0 && d.getUTCMinutes() === 0 && d.getUTCSeconds() === 0;
  const dateOnly = tender.deadlineIsDate ?? inferred;
  if (!dateOnly) return notClosed ? calm(getDeadline(deadline, ref)) : getCallDeadline(tender, ref);
  const info: DeadlineInfo = {
    ...getDeadline(new Date(d.getTime() + DAY_MS - 1000).toISOString(), ref),
    iso: deadline,
    utc: tender.deadlineIsDate ? formatDateLabelledUtc(deadline) : formatDateTimeUtc(deadline),
    dateOnly: true,
  };
  if (notClosed) return calm(info);
  if (tender.status !== 'closed' || info.state === 'closed') return info;
  return { ...info, state: 'closed', countdown: 'Closed', label: stateLabel('closed') };
}
