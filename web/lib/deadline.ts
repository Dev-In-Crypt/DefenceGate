import type { Call, CallStatus, DeadlineState, IsoDateTime, StatusKind, Tender } from './types';
import { formatDateLabelledUtc, formatDateTimeUtc, openingPassed } from './format';

/** Thresholds from the design system's deadline states. */
export const SOON_DAYS = 30;
export const URGENT_DAYS = 7;
/**
 * WP-106 (p01, p02, p04, p06): a tender is "Closing soon" within this many days only. At 30 days the chip stood on deadlines 19 to
 * 24 days ahead (and 32 days was "Open"); a bid team reads "closing soon" as about a week. Funding calls keep SOON_DAYS: their
 * list's "Closing soon" status is the API's 30 days.
 */
export const TENDER_SOON_DAYS = URGENT_DAYS;
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

export function deadlineState(deadline: IsoDateTime | null, ref: Date = now(), soonDays: number = SOON_DAYS): DeadlineState {
  const days = daysLeft(deadline, ref);
  if (days === null) return 'none';
  if (days < 0) return 'closed';
  if (days <= URGENT_DAYS) return 'urgent';
  if (days <= soonDays) return 'soon';
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
    normal: 'Deadline', soon: 'Closing soon', urgent: `Closes within ${URGENT_DAYS} days`, closed: 'Closed', none: 'No fixed deadline',
  }[state];
}

export function statusFromState(state: DeadlineState): StatusKind {
  if (state === 'closed') return 'closed';
  return state === 'normal' || state === 'none' ? 'open' : 'soon';
}

/**
 * Status pill for a call. A forthcoming call is "Opens soon" only while its dates allow it: a passed deadline
 * makes it closed, and a passed opening day makes it "Opening date passed" (the stored status is the source's
 * and can lag). "Closing soon" only refines an open call.
 */
export function callStatusKind(status: CallStatus, state: DeadlineState, openingDate: IsoDateTime | null = null, ref: Date = now()): StatusKind {
  if (status === 'forthcoming') {
    if (state === 'closed') return 'closed';
    if (openingDate && openingPassed(openingDate, ref)) return 'pending';
    return 'upcoming';
  }
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
  /** The source states a date, not a time of day. */
  dateOnly?: boolean;
  /** An open call past its latest cut-off that takes submissions continuously or in several cut-offs. */
  rolling?: boolean;
}

/**
 * The label of a deadline within URGENT_DAYS, in days and never by the week: "Closes this week" stood on Wednesday 28 October read on
 * Saturday 24 October (WP-106, p01), and on a notice closing today (site-qa2:N13).
 */
export function urgentLabel(days: number): string {
  if (days === 0) return 'Closes today';
  if (days === 1) return 'Closes tomorrow';
  return `Closes in ${days} days`;
}

/** Single entry point for all deadline presentation. `soonDays`: where "Closing soon" begins (TENDER_SOON_DAYS for a tender). */
export function getDeadline(deadline: IsoDateTime | null, ref: Date = now(), soonDays: number = SOON_DAYS): DeadlineInfo {
  const days = daysLeft(deadline, ref);
  const state = deadlineState(deadline, ref, soonDays);
  return {
    iso: deadline, days, state,
    utc: deadline === null ? '' : formatDateTimeUtc(deadline),
    countdown: countdownLabel(days),
    label: state === 'urgent' && days !== null ? urgentLabel(days) : stateLabel(state),
  };
}

/**
 * Deadline of a call. A source that gives a day and no time (`deadlineIsDate`, or a stamp at exactly 00:00 UTC on an
 * API that does not say) is shown as that date, with no time of day, on every page: a call is open to the end of
 * that day. An open call past its stored deadline is "Open: rolling submission" when the API says it takes
 * submissions continuously or in several cut-offs (`rolling`); otherwise it is closed. A call the API reports as
 * closed is shown closed even without a date.
 */
export function getCallDeadline(
  call: Pick<Call, 'status' | 'deadline'> & Partial<Pick<Call, 'deadlineIsDate' | 'rolling'>>,
  ref: Date = now(),
  soonDays: number = SOON_DAYS,
): DeadlineInfo {
  const { deadline } = call;
  let info = getDeadline(deadline, ref, soonDays);
  if (deadline !== null) {
    const d = new Date(deadline);
    const midnight = d.getUTCHours() === 0 && d.getUTCMinutes() === 0 && d.getUTCSeconds() === 0;
    if (call.deadlineIsDate ?? midnight) {
      // A stamp at 00:00 UTC is the start of the day it names; the call is open until that day ends.
      const basis = midnight ? new Date(d.getTime() + DAY_MS - 1000).toISOString() : deadline;
      info = { ...getDeadline(basis, ref, soonDays), iso: deadline, utc: formatDateLabelledUtc(deadline), dateOnly: true };
    }
  }
  if (call.status === 'open' && call.rolling === true && info.state === 'closed') {
    return { ...info, state: 'normal', countdown: '', label: 'Open: rolling submission', rolling: true };
  }
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
  if (deadline === null) return notClosed ? getDeadline(null, ref) : getCallDeadline(tender, ref, TENDER_SOON_DAYS);
  const d = new Date(deadline);
  const inferred = d.getUTCHours() === 0 && d.getUTCMinutes() === 0 && d.getUTCSeconds() === 0;
  const dateOnly = tender.deadlineIsDate ?? inferred;
  if (!dateOnly) return notClosed ? calm(getDeadline(deadline, ref, TENDER_SOON_DAYS)) : getCallDeadline(tender, ref, TENDER_SOON_DAYS);
  const info: DeadlineInfo = {
    ...getDeadline(new Date(d.getTime() + DAY_MS - 1000).toISOString(), ref, TENDER_SOON_DAYS),
    iso: deadline,
    utc: tender.deadlineIsDate ? formatDateLabelledUtc(deadline) : formatDateTimeUtc(deadline),
    dateOnly: true,
  };
  if (notClosed) return calm(info);
  if (tender.status !== 'closed' || info.state === 'closed') return info;
  return { ...info, state: 'closed', countdown: 'Closed', label: stateLabel('closed') };
}

/**
 * The time zone a buyer's deadline is meant in, by the buyer's country (the main zone of a country with several:
 * Spain's Canary Islands and Portugal's Azores keep their mainland's here). Only countries the sources carry.
 */
export const COUNTRY_TIME_ZONE: Record<string, string> = {
  DE: 'Europe/Berlin', PL: 'Europe/Warsaw', FR: 'Europe/Paris', CZ: 'Europe/Prague', ES: 'Europe/Madrid',
  RO: 'Europe/Bucharest', IT: 'Europe/Rome', GB: 'Europe/London', FI: 'Europe/Helsinki', NL: 'Europe/Amsterdam',
  DK: 'Europe/Copenhagen', SE: 'Europe/Stockholm', NO: 'Europe/Oslo', BG: 'Europe/Sofia', SI: 'Europe/Ljubljana',
  BE: 'Europe/Brussels', LT: 'Europe/Vilnius', LV: 'Europe/Riga', GR: 'Europe/Athens', EE: 'Europe/Tallinn',
  HR: 'Europe/Zagreb', HU: 'Europe/Budapest', PT: 'Europe/Lisbon', SK: 'Europe/Bratislava', IE: 'Europe/Dublin',
  AT: 'Europe/Vienna', CY: 'Asia/Nicosia', CH: 'Europe/Zurich', MT: 'Europe/Malta', LU: 'Europe/Luxembourg',
  IS: 'Atlantic/Reykjavik',
};

/**
 * "10:00 CEST (Warsaw)" for a deadline with a time of day, in the buyer's country; null for a date-only deadline, an
 * unknown country, or when the buyer's clock reads the same as UTC (the line would add nothing). A different day is
 * said ("00:30 CEST on 27 Nov"). The UTC form stays the stated one; this is a convenience, not a second deadline.
 */
export function localDeadline(iso: IsoDateTime | null, country: string | null | undefined, dateOnly = false): string | null {
  const zone = country ? COUNTRY_TIME_ZONE[country.toUpperCase()] : undefined;
  if (!iso || !zone || dateOnly) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime()) || (d.getUTCHours() === 0 && d.getUTCMinutes() === 0)) return null;
  const parts = (opts: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat('en-GB', { timeZone: zone, ...opts }).formatToParts(d);
  const get = (ps: Intl.DateTimeFormatPart[], t: string) => ps.find((p) => p.type === t)?.value ?? '';
  const clock = parts({ hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'short' });
  const day = parts({ day: 'numeric', month: 'short' });
  const time = `${get(clock, 'hour')}:${get(clock, 'minute')}`;
  const abbr = get(clock, 'timeZoneName');
  const utcTime = `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
  if (time === utcTime && /^(GMT|UTC)$/.test(abbr)) return null;
  const sameDay = Number(get(day, 'day')) === d.getUTCDate();
  const city = zone.split('/')[1].replace(/_/g, ' ');
  return `${time} ${abbr}${sameDay ? '' : ` on ${get(day, 'day')} ${get(day, 'month')}`} (${city})`;
}
