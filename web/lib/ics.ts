/**
 * iCalendar (RFC 5545) text for /calendar.ics. Only public fields of a notice go in: title, buyer or funder,
 * country, source name, link, deadline. No contact data exists in our records and none is added.
 */
import type { CalendarEntry } from './calendar';
import { absoluteUrl } from './seo';
import { countryName } from './taxonomy';

export const ICS_MAX_EVENTS = 500;
/** Said in the calendar file and on the page for a call with several cut-offs or continuous submission. */
export const ROLLING_NOTE = 'Continuous submission or several cut-offs: this is the next cut-off the source states (the last one when all have passed), and the call may stay open after it.';
/**
 * The EU Funding & Tenders Portal gives a day and no time (its reference data carries midnight UTC). All 38 call documents
 * we hold that state a time say 17:00:00 Brussels time (CET or CEST), so a call can close hours before the end of its day.
 * Nothing more is claimed: the file stays an all-day event and says so (V-B C1).
 */
export const EU_CUT_OFF_NOTE = 'No time is published; the call documents we have read set the cut-off at 17:00 Brussels time, so the call may close earlier that day.';
const isEuPortal = (e: CalendarEntry) => /funding\s*(?:&|and)\s*tenders/i.test(e.sourceName);
const SUMMARY_MAX = 120;
const DESCRIPTION_MAX = 1000;
const UID_DOMAIN = 'defencegatehub.com';
const EVENT_MINUTES = 30;
const encoder = new TextEncoder();

/** Lines are folded at 75 octets, never inside a UTF-8 sequence; a continuation line starts with one space. */
export function foldLine(line: string): string {
  if (encoder.encode(line).length <= 75) return line;
  const parts: string[] = [];
  let cur = '';
  let bytes = 0;
  let limit = 75;
  for (const ch of line) {
    const n = encoder.encode(ch).length;
    if (bytes + n > limit) { parts.push(cur); cur = ''; bytes = 0; limit = 74; }
    cur += ch;
    bytes += n;
  }
  parts.push(cur);
  return parts.join('\r\n ');
}

/** Plain text of a TEXT value: control characters out, length capped, then \ ; , and line breaks escaped. */
export function icsText(value: string, max: number): string {
  const clean = value.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim();
  const chars = Array.from(clean);
  const capped = chars.length > max ? `${chars.slice(0, max - 1).join('').trimEnd()}…` : clean;
  return capped.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,');
}

const stamp = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
const dateValue = (d: Date) => stamp(d).slice(0, 8);

function event(e: CalendarEntry, dtstamp: string): string[] {
  const start = new Date(e.deadline);
  const url = absoluteUrl(e.href);
  const kind = e.kind === 'tender' ? 'Tender' : 'Funding call';
  const opens = e.event === 'opens';
  // An opening and a call's planned deadline are their own events (own UID), so a calendar shows both and the
  // deadline keeps its UID when the call opens.
  const word = opens ? 'Opens' : e.planned ? 'Deadline, call not open yet' : e.rolling ? 'Cut-off' : 'Deadline';
  const description = [
    `${kind}: ${e.who}${e.country ? ` (${countryName(e.country)})` : ''}.`,
    opens ? `Planned opening ${e.when}. The source may move it.` : e.rolling ? `Cut-off ${e.when}.` : `Deadline ${e.when}.`,
    e.dateOnly && !opens ? (isEuPortal(e) && e.kind === 'funding' ? EU_CUT_OFF_NOTE : 'The source publishes a day and no time.') : null,
    e.planned && !opens ? 'The call has not opened: the date is the source’s plan.' : null,
    e.note,
    `Source: ${e.sourceName}.`,
    'The original notice is authoritative: check it at the source before you act.',
    url,
  ].filter(Boolean).join(' ');
  const lines = ['BEGIN:VEVENT', `UID:${e.key}@${UID_DOMAIN}`, `DTSTAMP:${dtstamp}`];
  if (e.dateOnly) {
    const next = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate() + 1));
    lines.push(`DTSTART;VALUE=DATE:${dateValue(start)}`, `DTEND;VALUE=DATE:${dateValue(next)}`);
  } else {
    lines.push(`DTSTART:${stamp(start)}`, `DTEND:${stamp(new Date(start.getTime() + EVENT_MINUTES * 60_000))}`);
  }
  lines.push(
    `SUMMARY:${icsText(`${word}: ${e.title}`, SUMMARY_MAX)}`,
    `DESCRIPTION:${icsText(description, DESCRIPTION_MAX)}`,
    `URL:${url}`,
    'TRANSP:TRANSPARENT',
    'END:VEVENT',
  );
  return lines;
}

/** The calendar file, CRLF lines, at most ICS_MAX_EVENTS events in the order given. */
export function buildIcs(entries: CalendarEntry[], at: Date = new Date()): string {
  const dtstamp = stamp(at);
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//DefenceGate//Deadline calendar//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    'X-WR-CALNAME:DefenceGate deadlines',
    `X-WR-CALDESC:${icsText('Deadlines of open defence tenders and funding calls, and the opening days of calls that have not opened, in UTC. The original notice is authoritative.', DESCRIPTION_MAX)}`,
    ...entries.slice(0, ICS_MAX_EVENTS).flatMap((e) => event(e, dtstamp)),
    'END:VCALENDAR',
  ];
  return `${lines.map(foldLine).join('\r\n')}\r\n`;
}
