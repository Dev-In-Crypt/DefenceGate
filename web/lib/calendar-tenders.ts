/**
 * The tender half of the deadline calendar: what an entry is, and how the API's calendar item (GET /v1/tenders/calendar:
 * every open notice that states a deadline) becomes one. Pure and import-light (no data layer): lib/wp52b.check.ts runs it.
 */
import { getTenderDeadline } from './deadline';
import { anomalyNotes, isLongRunning, tenderStatusView } from './tender-status';
import type { CalendarItem } from './types';

export type CalendarKind = 'tender' | 'funding';
/** A deadline, or the day a funding call opens (only in the calendar file: the page lists deadlines). */
export type CalendarEvent = 'deadline' | 'opens';

export interface CalendarEntry {
  /** `<kind>-<id>` (`funding-<id>-opens` for an opening): also the stable part of the calendar-file UID. */
  key: string;
  kind: CalendarKind;
  event: CalendarEvent;
  /** A funding call that has not opened yet: its deadline is the source's planned one. */
  planned?: boolean;
  /** A funding call that takes submissions continuously or in several cut-offs: its date is the latest cut-off, not the end. */
  rolling?: boolean;
  id: string;
  title: string;
  /** Site path of the detail page. */
  href: string;
  /** ISO UTC. For an opening, the opening day. */
  deadline: string;
  /** The source gives a date, not a time of day. */
  dateOnly: boolean;
  /** "13 Oct 2026 (date only)" or "13 Oct 2026, 16:00 UTC". */
  when: string;
  /** The buyer, or the funder of a call. */
  who: string;
  /** ISO-2 of the buyer; the funder country (or EU) of a call. */
  country: string | null;
  sourceName: string;
  /** A known anomaly of the source's dates, in words. */
  note: string | null;
}

/**
 * One entry of the calendar from the API's item, or why there is none. `long`: a deadline over three years ahead
 * (framework agreements, DPS) is a notice that stays open, not a date to plan around, and is left off and counted.
 * The item carries the deadline the notice's page shows, so the entry and the page agree.
 */
export function entryFromItem(item: CalendarItem, ref: Date): { entry: CalendarEntry | null; long: boolean } {
  const view = tenderStatusView(item, ref);
  if (view.kind !== 'open' && view.kind !== 'soon') return { entry: null, long: false };
  if (isLongRunning(item)) return { entry: null, long: true };
  const d = getTenderDeadline(item, ref);
  if (!d.iso || d.state === 'closed') return { entry: null, long: false };
  return {
    long: false,
    entry: {
      key: `tender-${item.id}`, kind: 'tender', event: 'deadline', id: item.id, title: item.title, href: `/tenders/${item.slug}`,
      deadline: d.iso, dateOnly: d.dateOnly === true, when: d.utc,
      who: item.buyerName, country: item.country, sourceName: item.sourceName, note: anomalyNotes(item)[0] ?? null,
    },
  };
}

/** The 1-based page of an agenda of `size` entries on which the first entry of `day` (`YYYY-MM-DD`) stands; 1 when the day has none. */
export function pageOfDay(entries: Pick<CalendarEntry, 'deadline'>[], day: string, size: number): number {
  const at = entries.findIndex((e) => new Date(e.deadline).toISOString().slice(0, 10) === day);
  return at < 0 ? 1 : Math.floor(at / size) + 1;
}
