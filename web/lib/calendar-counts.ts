/**
 * WP-87: what the deadline calendar says beside its counts, so that its numbers and the lists' agree or say why they differ
 * (UX audit 22 October 2026: 1,486 tenders with a deadline ahead on the list, 1,390 on the calendar; 63 open calls on /funding,
 * 58 on the calendar; a feed silently cut at 500). Pure and free of the data layer: lib/wp87.check.ts runs it.
 */
import { CALENDAR_PARAMS, ignoredFilters, toTenderQuery, unknownParams, type SearchParams } from './filters';
import { formatNumber, plural } from './format';

const count = (n: number, one: string) => `${formatNumber(n)} ${plural(n, one)}`;
import type { TenderFilters } from './types';

type TenderPart = Pick<TenderFilters, 'q' | 'cpv' | 'cpvMain' | 'notCpv' | 'scope' | 'goods' | 'deadlineFrom' | 'deadlineTo' | 'valueMin' | 'valueMax' | 'currency'>;
interface Params { kind: 'all' | 'tenders' | 'funding'; countries: string[]; tender: TenderPart }

/** The filters that only a tender has: a funding call has no CPV code, scope or estimated value, and the search is the tender list's. */
export function tenderOnly(t: TenderPart | undefined): string[] {
  if (!t) return [];
  return [
    t.q ? 'the search' : null, t.cpv || t.notCpv ? 'the CPV code' : null, t.scope ? 'the scope' : null, t.goods ? 'Defence goods only' : null,
    t.valueMin !== undefined || t.valueMax !== undefined || t.currency ? 'the estimated value' : null,
  ].filter((s): s is string => s !== null);
}

const words = (list: string[]) => (list.length < 2 ? list.join('') : `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`);

/** What the calendar was asked and does not read, and a tender filter that cannot narrow the funding calls: said above the entries. */
export function calendarNotices(sp: SearchParams, p: Params): string[] {
  const { status: _s, sort: _o, page: _p, country: _c, kind: _k, view: _v, month: _m, ...tenderParams } = sp;
  const only = tenderOnly(p.tender);
  return [
    ...unknownParams(sp, CALENDAR_PARAMS),
    ...ignoredFilters(tenderParams, 'tenders'),
    ...(only.length > 0 && p.kind === 'all' ? [`Funding calls are not listed: ${words(only)} ${only.length === 1 ? 'applies' : 'apply'} to tenders only.`] : []),
    ...(only.length > 0 && p.kind === 'funding' ? [`Ignored for funding calls: ${words(only)} (tenders only).`] : []),
  ];
}

export interface CountLine { key: string; text: string; href?: string; link?: string }

export interface CalendarCountsInput {
  tendersOk: boolean; callsOk: boolean;
  /** Open tenders with a deadline under the filters, as the API counts them: the tenders list's count of the same filters. */
  tendersHeld: number;
  longRunning: number;
  /** WP-96: open tenders of the filters that state no deadline: on the tenders list, never on a calendar. */
  withoutDeadline?: number;
  openCalls: (string | null)[];
}

/** WP-96: the sentence for the open tenders without a deadline, which a calendar leaves out: said, never silent. */
export function withoutDeadlineLine(n: number): string {
  return n > 0
    ? `${formatNumber(n)} open ${n === 1 ? 'tender states' : 'tenders state'} no deadline: the tenders list shows ${n === 1 ? 'it' : 'them'}, the calendar cannot.`
    : '';
}

/**
 * The calendar's counts beside the lists' (`shown`: the entries the calendar lists for these filters). Tenders: the tenders list
 * with a deadline from today counts the same open notices, and the long-running ones the calendar leaves off are named. Funding:
 * /funding counts every open call; the ones with no coming deadline (continuous submission past the last cut-off, or none stated)
 * are named. `today` is YYYY-MM-DD.
 */
export function calendarCounts(data: CalendarCountsInput, p: Params, shown: { tenders: number; calls: number }, today: string): CountLine[] {
  const out: CountLine[] = [];
  if (p.kind !== 'funding' && data.tendersOk) {
    const listCountries = p.countries.filter((c) => c !== 'EU');
    const href = `/tenders${toTenderQuery({ ...p.tender, country: listCountries.length > 0 ? listCountries : undefined, deadlineFrom: p.tender.deadlineFrom ?? today })}`;
    const other = Math.max(0, data.tendersHeld - shown.tenders - data.longRunning);
    const reasons = [
      data.longRunning > 0 ? `${formatNumber(data.longRunning)} ${data.longRunning === 1 ? 'has' : 'have'} a deadline more than 3 years ahead (framework agreements and dynamic purchasing systems that stay open) and ${data.longRunning === 1 ? 'is' : 'are'} left off` : null,
      other > 0 ? `${formatNumber(other)} could not be placed on a day` : null,
    ].filter(Boolean);
    const undated = withoutDeadlineLine(data.withoutDeadline ?? 0);
    out.push({
      key: 'tenders',
      text: (data.tendersHeld === shown.tenders
        ? `Tenders: ${count(shown.tenders, 'deadline')}, every open tender with a deadline ahead under these filters, as the tenders list counts them.`
        : `Tenders: ${count(shown.tenders, 'deadline')} of the ${formatNumber(data.tendersHeld)} open tenders with a deadline ahead that the tenders list counts under these filters; ${words(reasons as string[])}.`)
        + (undated ? ` ${undated}` : ''),
      href, link: 'Open that list',
    });
  }
  if (p.kind !== 'tenders' && data.callsOk && !(p.kind === 'all' && tenderOnly(p.tender).length > 0)) {
    const dated = Boolean(p.tender.deadlineFrom || p.tender.deadlineTo);
    const open = data.openCalls.filter((c) => p.countries.length === 0 || (c !== null && p.countries.includes(c))).length;
    const left = Math.max(0, open - shown.calls);
    out.push({
      key: 'funding',
      text: dated || left === 0
        ? `Funding calls: ${count(shown.calls, 'deadline')}${dated ? ' in the dates chosen' : ', every open call'}.`
        : `Funding calls: ${count(shown.calls, 'deadline')} of the ${formatNumber(open)} open calls the funding list counts; ${formatNumber(left)} ${left === 1 ? 'has' : 'have'} no coming deadline (submission continues past the last cut-off, or no date is stated).`,
    });
  }
  return out;
}

/** The feed's size, said under its address: every event, or where a ceiling cuts it. */
export function feedLine(events: number, max = 5000): string {
  return events > max
    ? `It holds the first ${formatNumber(max)} of the ${formatNumber(events)} events these filters give; narrow them for the rest.`
    : `It holds every one of the ${formatNumber(events)} events these filters give.`;
}
