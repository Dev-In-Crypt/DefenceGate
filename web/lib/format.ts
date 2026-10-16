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

const NOTICE_KIND_LABELS: Record<string, string> = {
  call: 'Call notice', prior: 'Prior information notice', award: 'Award notice',
  formalisation: 'Contract formalisation notice', cancellation: 'Cancellation notice', update: 'Notice',
};

/**
 * "Award notice dated 12 Sep 2026": what the source gave in place of a publication date. Null when it gave
 * neither. A kind this build does not know reads as plain "Notice", never as a publication.
 */
export function noticeDateLabel(t: { noticeDate?: IsoDateTime | null; noticeKind?: string | null }): string | null {
  if (!t.noticeDate) return null;
  const kind = NOTICE_KIND_LABELS[t.noticeKind ?? ''] ?? 'Notice';
  return `${kind} dated ${formatDateUtc(t.noticeDate)}`;
}

/** "13 Oct 2026 (date only)": a date without a time of day says so, instead of a dangling "UTC". */
export function formatDateLabelledUtc(iso: IsoDateTime): string {
  return `${formatDateUtc(iso)} (date only)`;
}

/**
 * "26 Nov 2026, 16:00 UTC". A time of exactly 00:00 UTC is how a source that gives only a
 * date arrives (the EU calendar does), so it is shown as a date and says so, instead of
 * claiming a closing time nobody stated.
 */
export function formatDateTimeUtc(iso: IsoDateTime): string {
  const d = new Date(iso);
  if (d.getUTCHours() === 0 && d.getUTCMinutes() === 0) return `${formatDateUtc(iso)} (time not stated)`;
  return `${formatDateUtc(iso)}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

/**
 * The opening of a call that has not opened. A planned date that has already passed is
 * said to be a plan: the source still lists the call as forthcoming, so it is not open.
 */
export function openingPhrase(iso: IsoDateTime, ref: Date = new Date()): { lead: string; date: string } {
  return { lead: openingPassed(iso, ref) ? 'Opening was planned for' : 'Opens', date: formatDateLabelledUtc(iso) };
}

/** The day of a planned opening is before today (UTC). The stored status is the source's; the dates decide. */
export function openingPassed(iso: IsoDateTime, ref: Date = new Date()): boolean {
  return new Date(iso).getTime() < Date.UTC(ref.getUTCFullYear(), ref.getUTCMonth(), ref.getUTCDate());
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

/**
 * Amounts at or below this are placeholders: 0, 0.01 and 1 are what a publisher types when no value is known.
 * They are shown as not stated, left out of exports, and never matched by a value filter.
 */
export const PLACEHOLDER_AMOUNT_MAX = 1;
export function isPlaceholderAmount(amount: number): boolean {
  return !(amount > PLACEHOLDER_AMOUNT_MAX);
}

/**
 * The calls whose call-level budget (`budgetScope: 'call'`) already appeared earlier in this list: the amount is
 * shown once, on the first topic, and the others say it is shared. A topic budget is each topic's own.
 */
export function repeatedCallBudgets(calls: { id: string; callId: string | null; budget: Money | null; budgetScope: 'call' | 'topic' | null }[]): Set<string> {
  const seen = new Set<string>();
  const repeats = new Set<string>();
  for (const c of calls) {
    if (c.budgetScope !== 'call' || !c.budget || !c.callId) continue;
    const key = `${c.callId}|${c.budget.currency}|${c.budget.amount}`;
    if (seen.has(key)) repeats.add(c.id);
    else seen.add(key);
  }
  return repeats;
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

/** "European Commission · European Defence Fund": who pays and the programme in full; said once when they are the same. */
export function funderLine(c: { funder: string; programmeName: string }): string {
  return c.funder === c.programmeName ? c.funder : `${c.funder} · ${c.programmeName}`;
}
