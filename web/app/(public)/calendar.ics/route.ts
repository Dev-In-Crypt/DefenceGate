import { filterEntries, loadCalendar, parseCalendarParams } from '@/lib/calendar';
import { searchParamsOf } from '@/lib/export';
import { CALENDAR_PARAMS, unknownParams } from '@/lib/filters';
import { ICS_MAX_EVENTS, buildIcs } from '@/lib/ics';

/**
 * The deadline calendar as an iCalendar file: open tenders and funding calls with a deadline, soonest first, and
 * for each funding call that has not opened its opening day and planned deadline as events of their own,
 * every event the filters give (ICS_MAX_EVENTS is a ceiling the description names when it cuts). `kind` (all, tenders, funding),
 * `country` and the tender list's filters (WP-87) narrow it like the page; any other parameter is a 422. Cached for an hour.
 */
export async function GET(request: Request): Promise<Response> {
  const sp = searchParamsOf(new URL(request.url));
  // WP-87: a feed cannot show a notice, so a parameter it does not read is refused, never dropped in silence
  const unknown = unknownParams(sp, CALENDAR_PARAMS);
  if (unknown.length > 0) {
    return new Response(`${unknown.join('\n')}\nThe calendar feed reads: ${CALENDAR_PARAMS.join(', ')}.`, {
      status: 422, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  const p = parseCalendarParams(sp);
  const { kind, countries } = p;
  const data = await loadCalendar(undefined, { ...p.tender, country: countries.length > 0 ? countries : undefined }).catch(() => null);
  // Half a calendar presented as the whole one would mislead a subscriber: a failing source is an error.
  if (!data || (!data.tendersOk && kind !== 'funding') || (!data.callsOk && kind !== 'tenders')) {
    return new Response('The calendar could not be built right now. Try again in a few minutes.', {
      status: 502, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  const hour = new Date();
  hour.setUTCMinutes(0, 0, 0);
  // Deadlines of open notices, then the opening days and planned deadlines of funding calls that have not opened.
  const events = [...data.entries, ...data.upcoming].sort(
    (a, b) => new Date(a.deadline).getTime() - new Date(b.deadline).getTime() || a.key.localeCompare(b.key));
  const chosen = filterEntries(events, p);
  return new Response(buildIcs(chosen, hour, { tendersBeyond: data.tendersTotal - data.tendersHeld }), {
    headers: {
      'content-type': 'text/calendar; charset=utf-8',
      'content-disposition': 'inline; filename="defencegate-deadlines.ics"',
      'cache-control': 'public, max-age=3600',
      // how many events the file holds of how many the filters give: equal unless a cap cut it (the description says so too)
      'x-dg-events': `${Math.min(chosen.length, ICS_MAX_EVENTS)} of ${chosen.length}`,
    },
  });
}
