import type { IsoDateTime, Money } from './types';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'] as const;
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;
const pad = (n: number) => String(n).padStart(2, '0');
const amountFormat = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });

/** "26 Nov 2026" (UTC) */
export function formatDateUtc(iso: IsoDateTime): string {
  const d = new Date(iso);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** "13 Oct 2026, UTC": a date without a time of day, still labelled. */
export function formatDateLabelledUtc(iso: IsoDateTime): string {
  return `${formatDateUtc(iso)}, UTC`;
}

/**
 * "26 Nov 2026, 16:00 UTC". A time of exactly 00:00 UTC is how a source that gives only a
 * date arrives (the EU calendar does), so it is shown as a date and says so, instead of
 * claiming a closing time nobody stated.
 */
export function formatDateTimeUtc(iso: IsoDateTime): string {
  const d = new Date(iso);
  if (d.getUTCHours() === 0 && d.getUTCMinutes() === 0) return `${formatDateUtc(iso)}, UTC (time not stated)`;
  return `${formatDateUtc(iso)}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

/**
 * The opening of a call that has not opened. A planned date that has already passed is
 * said to be a plan: the source still lists the call as forthcoming, so it is not open.
 */
export function openingPhrase(iso: IsoDateTime, ref: Date = new Date()): { lead: string; date: string } {
  const planned = new Date(iso).getTime() < Date.UTC(ref.getUTCFullYear(), ref.getUTCMonth(), ref.getUTCDate());
  return { lead: planned ? 'Opening was planned for' : 'Opens', date: formatDateLabelledUtc(iso) };
}

/** "November 2026" */
export function formatMonthUtc(iso: IsoDateTime): string {
  const d = new Date(iso);
  return `${MONTHS_LONG[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function dayParts(iso: IsoDateTime): { day: string; month: string; weekday: string } {
  const d = new Date(iso);
  return { day: String(d.getUTCDate()), month: MONTHS[d.getUTCMonth()], weekday: WEEKDAYS[d.getUTCDay()] };
}

/** "EUR 25,000,000" — always ISO code, never a symbol. */
export function formatMoney(m: Money): string {
  return `${m.currency} ${amountFormat.format(m.amount)}`;
}

export function formatNumber(n: number): string {
  return amountFormat.format(n);
}

export function formatPercent(share: number): string {
  return `${Math.round(share * 100)}%`;
}
