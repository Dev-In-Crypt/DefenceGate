import { filterEntries, loadCalendar, parseCalendarParams } from '@/lib/calendar';
import { searchParamsOf } from '@/lib/export';
import { buildIcs } from '@/lib/ics';

/**
 * The deadline calendar as an iCalendar file: open tenders and funding calls with a deadline, soonest first,
 * at most 500 events. `kind` (all, tenders, funding) and `country` narrow it like the page. Cached for an hour.
 */
export async function GET(request: Request): Promise<Response> {
  const { kind, countries } = parseCalendarParams(searchParamsOf(new URL(request.url)));
  const data = await loadCalendar().catch(() => null);
  // Half a calendar presented as the whole one would mislead a subscriber: a failing source is an error.
  if (!data || (!data.tendersOk && kind !== 'funding') || (!data.callsOk && kind !== 'tenders')) {
    return new Response('The calendar could not be built right now. Try again in a few minutes.', {
      status: 502, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  const hour = new Date();
  hour.setUTCMinutes(0, 0, 0);
  return new Response(buildIcs(filterEntries(data.entries, { kind, countries }), hour), {
    headers: {
      'content-type': 'text/calendar; charset=utf-8',
      'content-disposition': 'inline; filename="defencegate-deadlines.ics"',
      'cache-control': 'public, max-age=3600',
    },
  });
}
