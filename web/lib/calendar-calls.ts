/**
 * The calendar entries of one funding call (WP-91: the deadline calendar, the feed of a funding search and the file of one call read this
 * one rule). Import-light, no data layer: lib/wp91.check.ts runs it.
 *
 * A call that has not opened: its opening day, still to come, and its planned deadline. An open call: its deadline, unless it is a
 * rolling call past its last cut-off (open, with no coming date). A closed call: none.
 */
import type { CalendarEntry } from './calendar-tenders';
import { getCallDeadline } from './deadline';
import { formatDateLabelledUtc } from './format';
import { ROLLING_NOTE } from './ics';
import type { Call } from './types';

const CALL_SLUG = /^[0-9]{1,9}(-[a-z0-9-]{0,80})?$/;          // the API's own (lib/api.ts isCallSlug)
const dayOf = (iso: string) => new Date(iso).toISOString().slice(0, 10);

export function callEntries(c: Call, ref: Date): CalendarEntry[] {
  if (!CALL_SLUG.test(c.slug)) return [];
  const base = { kind: 'funding', id: c.id, title: c.title, href: `/funding/${c.slug}`, who: c.issuer ?? c.programmeName,
    country: c.funderCountry, sourceName: c.source.sourceName, note: null } as const;
  const d = getCallDeadline(c, ref);
  const out: CalendarEntry[] = [];
  if (c.status === 'forthcoming') {
    if (c.openingDate && dayOf(c.openingDate) >= ref.toISOString().slice(0, 10)) {
      out.push({ ...base, key: `funding-${c.id}-opens`, event: 'opens', deadline: c.openingDate, dateOnly: true, when: formatDateLabelledUtc(c.openingDate) });
    }
    if (c.deadline && d.iso && d.state !== 'closed') {
      out.push({ ...base, key: `funding-${c.id}`, event: 'deadline', planned: true, deadline: c.deadline, dateOnly: d.dateOnly === true, when: d.utc });
    }
  } else if (c.status === 'open' && c.deadline && d.iso && d.state !== 'closed' && !d.rolling) {
    // The source's date is a cut-off of a call that keeps taking submissions: the file must not call it the end.
    out.push({ ...base, key: `funding-${c.id}`, event: 'deadline', deadline: c.deadline, dateOnly: d.dateOnly === true, when: d.utc,
      rolling: c.rolling === true, note: c.rolling === true ? ROLLING_NOTE : null });
  }
  return out;
}
