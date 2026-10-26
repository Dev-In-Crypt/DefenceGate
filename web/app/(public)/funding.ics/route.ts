import { withEtag } from '@/lib/etag';
import { getCall, REMOVED, whenRemoved } from '@/lib/api';
import { callEntries, loadFundingSearch } from '@/lib/calendar';
import { now } from '@/lib/deadline';
import { searchParamsOf } from '@/lib/export';
import { describeCallFilters, ignoredFilters, parseCallFilters, unknownParams } from '@/lib/filters';
import { buildIcs } from '@/lib/ics';

const PLAIN = 'text/plain; charset=utf-8';
/** The filters of /funding (lib/filters.ts parseCallFilters); the page and the view are the list's, and are left out. */
const SEARCH_PARAMS = ['q', 'programme', 'regime', 'country', 'status', 'from', 'to', 'min', 'max', 'currency', 'sort', 'cascade', 'ukraine', 'uaNoFunding', 'who'] as const;
const CALL_SLUG = /^[0-9]{1,9}(-[a-z0-9-]{0,80})?$/;

const refuse = (status: number, text: string) => new Response(text, { status, headers: { 'content-type': PLAIN, 'cache-control': 'no-store' } });

function calendar(body: string, filename: string, disposition: 'inline' | 'attachment' = 'inline', events?: number): Response {
  return new Response(body, {
    headers: {
      'content-type': 'text/calendar; charset=utf-8',
      'content-disposition': `${disposition}; filename="${filename}"`,
      'cache-control': 'public, max-age=3600',
      ...(events !== undefined ? { 'x-dg-events': String(events) } : {}),
    },
  });
}

/**
 * WP-91 (UX audit 6): calendar files of funding calls.
 *
 *   /funding.ics?call=<slug>   one call's dates: its deadline, or, before it opens, its opening day and planned deadline (the rule of the
 *                              deadline calendar, `callEntries`); a closed call, or one without a date to come, is 404 with the reason
 *   /funding.ics?<filters>     a funding search, with exactly the filters of /funding: an Open list gives its deadlines, Opens soon the
 *                              opening days and planned deadlines, All both; a Closed list has no dates to come and is refused
 *
 * A parameter the file does not read, or a value it cannot use, is refused (as /calendar.ics, WP-87). Cached for an hour.
 */
/** WP-114: with an ETag, and 304 for a reader who holds the same file (`lib/etag.ts`). */
export async function GET(request: Request): Promise<Response> {
  return withEtag(request, await build(request));
}

async function build(request: Request): Promise<Response> {
  const sp = searchParamsOf(new URL(request.url));
  const hour = new Date();
  hour.setUTCMinutes(0, 0, 0);

  if (sp.call !== undefined) {
    const slug = typeof sp.call === 'string' ? sp.call : '';
    if (Object.keys(sp).length > 1 || !CALL_SLUG.test(slug)) return refuse(422, 'call: one call slug, and no other parameter.');
    const call = await getCall(slug).catch(whenRemoved).catch(() => undefined);
    if (call === undefined) return refuse(502, 'The call could not be read right now. Try again in a few minutes.');
    if (call === REMOVED || !call) return refuse(404, 'No such call.');
    const entries = callEntries(call, now());
    if (entries.length === 0) return refuse(404, 'This call has no date to come (it has closed, or the source states none).');
    return calendar(buildIcs(entries, hour, { name: call.title, about: 'The dates of one funding call on DefenceGate, in UTC.' }),
      `defencegate-call-${call.id}.ics`, 'attachment');
  }

  const { page: _p, view: _v, ...rest } = sp;
  const notices = [...unknownParams(rest, SEARCH_PARAMS), ...ignoredFilters(rest, 'funding')];
  if (notices.length > 0) return refuse(422, [...notices, 'The file reads the filters of /funding, or call=<slug>.'].join('\n'));
  const f = parseCallFilters(rest);
  const data = await loadFundingSearch(f).catch(() => undefined);
  if (data === null) return refuse(422, 'A list of closed calls has no dates to come: choose Open, Opens soon or All for a calendar.');
  if (data === undefined) return refuse(502, 'The calendar could not be built right now. Try again in a few minutes.');
  const cut = data.total > 500 ? ` It holds the first 500 calls of ${data.total} for each status; narrow the filters for the rest.` : '';
  const undated = data.undated > 0 ? ` ${data.undated} ${data.undated === 1 ? 'call of this search states no deadline (or no date to come) and is' : 'calls of this search state no deadline (or no date to come) and are'} not in it; the funding list has ${data.undated === 1 ? 'it' : 'them'}.` : '';
  return calendar(buildIcs(data.entries, hour, {
    name: 'DefenceGate funding search',
    about: `Funding calls of one search on DefenceGate (${describeCallFilters(f).join(', ')}): deadlines, and the opening days of calls that have not opened, in UTC.${cut}${undated}`,
  }), 'defencegate-funding-search.ics', 'inline', data.entries.length);
}
