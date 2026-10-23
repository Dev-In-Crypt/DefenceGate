/**
 * Data of the deadline calendar (/calendar and /calendar.ics): the open defence tenders and the open funding
 * calls that have a deadline, from the public API helpers only. Nothing is converted or invented: an entry is
 * the notice's own deadline.
 */
import { getCalls, getTenderCalendar, isCallSlug, isTenderSlug } from './api';
import { entryFromItem, type CalendarEntry } from './calendar-tenders';
import { getCallDeadline, now } from './deadline';
import { formatDateLabelledUtc } from './format';
import { tenderOnly } from './calendar-counts';
import { ROLLING_NOTE } from './ics';
import { DEFAULT_TENDER_SCOPE, parseTenderFilters, toTenderQuery, type SearchParams } from './filters';
import type { TenderFilters } from './types';

export type { CalendarEntry, CalendarEvent, CalendarKind } from './calendar-tenders';
export type KindFilter = 'all' | 'tenders' | 'funding';
export type CalendarView = 'list' | 'month';

export interface CalendarData {
  entries: CalendarEntry[];
  /** Funding calls that have not opened: the day each opens and its planned deadline. For the calendar file. */
  upcoming: CalendarEntry[];
  tendersOk: boolean;
  callsOk: boolean;
  /** Open tenders in total, and how many the calendar holds (the earliest deadlines first). */
  tendersTotal: number;
  tendersHeld: number;
  /** Open tenders left off because their deadline is over three years ahead (framework agreements, DPS). */
  longRunning: number;
  /**
   * WP-87: the funder country (null: EU) of every open call, as /funding counts them: the calendar lists only those with a
   * coming deadline, so the page says how many of the open calls it holds and why the others are not on it.
   */
  openCalls: (string | null)[];
}

const CALL_PAGE = 500;

const dayOf = (iso: string) => new Date(iso).toISOString().slice(0, 10);

/**
 * The open tenders with a deadline, all of them in one read (GET /v1/tenders/calendar). The calendar used to read five
 * pages of the list, the 500 earliest of 1,529, and November showed none of its 593 (UX audit T9).
 */
async function loadTenders(ref: Date, filters: TenderFilters): Promise<{ entries: CalendarEntry[]; total: number; held: number; longRunning: number }> {
  const page = await getTenderCalendar(filters);
  const entries: CalendarEntry[] = [];
  let longRunning = 0;
  for (const item of page.items) {
    if (!isTenderSlug(item.slug)) continue;
    const r = entryFromItem(item, ref);
    // A deadline 2030 to 2034 is a notice that stays open, not a date to plan around (site-qa2:N7).
    if (r.long) longRunning += 1;
    else if (r.entry) entries.push(r.entry);
  }
  return { entries, total: Math.max(page.total, page.items.length), held: page.items.length, longRunning };
}

/** Calls that have not opened yet (`Opens soon`): the opening day, still to come, and the planned deadline. */
export async function loadUpcomingCalls(ref: Date): Promise<CalendarEntry[]> {
  const r = await getCalls({ status: 'forthcoming', pageSize: CALL_PAGE, page: 1 }, { cacheable: true });
  const today = ref.toISOString().slice(0, 10);
  const entries: CalendarEntry[] = [];
  for (const c of r.items) {
    if (c.status !== 'forthcoming' || !isCallSlug(c.slug)) continue;
    const base = { kind: 'funding', id: c.id, title: c.title, href: `/funding/${c.slug}`, who: c.issuer ?? c.programmeName,
      country: c.funderCountry, sourceName: c.source.sourceName, note: null } as const;
    if (c.openingDate && dayOf(c.openingDate) >= today) {
      entries.push({ ...base, key: `funding-${c.id}-opens`, event: 'opens', deadline: c.openingDate, dateOnly: true, when: formatDateLabelledUtc(c.openingDate) });
    }
    const d = getCallDeadline(c, ref);
    if (c.deadline && d.iso && d.state !== 'closed') {
      entries.push({ ...base, key: `funding-${c.id}`, event: 'deadline', planned: true, deadline: c.deadline, dateOnly: d.dateOnly === true, when: d.utc });
    }
  }
  return entries;
}

async function loadCalls(ref: Date): Promise<{ entries: CalendarEntry[]; upcoming: CalendarEntry[]; openCalls: (string | null)[] }> {
  const [r, upcoming] = await Promise.all([getCalls({ status: 'open', pageSize: CALL_PAGE, page: 1 }, { cacheable: true }), loadUpcomingCalls(ref)]);
  const entries: CalendarEntry[] = [];
  for (const c of r.items) {
    const d = getCallDeadline(c, ref);
    // A rolling call past its last cut-off is open but has no coming deadline to put on a calendar.
    if (c.status !== 'open' || !c.deadline || !d.iso || d.state === 'closed' || d.rolling || !isCallSlug(c.slug)) continue;
    entries.push({
      key: `funding-${c.id}`, kind: 'funding', event: 'deadline', id: c.id, title: c.title, href: `/funding/${c.slug}`,
      deadline: c.deadline, dateOnly: d.dateOnly === true, when: d.utc,
      who: c.issuer ?? c.programmeName, country: c.funderCountry, sourceName: c.source.sourceName,
      // The source's date is a cut-off of a call that keeps taking submissions: the file must not call it the end.
      rolling: c.rolling === true, note: c.rolling === true ? ROLLING_NOTE : null,
    });
  }
  return { entries, upcoming, openCalls: r.items.filter((c) => c.status === 'open').map((c) => c.funderCountry ?? null) };
}

const byTime = (a: CalendarEntry, b: CalendarEntry) => new Date(a.deadline).getTime() - new Date(b.deadline).getTime() || a.key.localeCompare(b.key);

/**
 * Tenders and calls together, soonest deadline first. A failing half is reported, not hidden. `tender` (WP-87): the tender list's
 * filters, applied by the API to the tenders as the list applies them; the calls are narrowed by `filterEntries`.
 */
export async function loadCalendar(ref: Date = now(), tender: TenderFilters = {}): Promise<CalendarData> {
  const [t, c] = await Promise.all([
    loadTenders(ref, tender).then((v) => ({ ok: true as const, ...v })).catch(() => ({ ok: false as const, entries: [] as CalendarEntry[], total: 0, held: 0, longRunning: 0 })),
    loadCalls(ref).then((v) => ({ ok: true as const, ...v })).catch(() => ({ ok: false as const, entries: [] as CalendarEntry[], upcoming: [] as CalendarEntry[], openCalls: [] as (string | null)[] })),
  ]);
  const entries = [...t.entries, ...c.entries].sort(byTime);
  return {
    entries, upcoming: c.upcoming.sort(byTime), tendersOk: t.ok, callsOk: c.ok, tendersTotal: t.total, tendersHeld: t.held,
    longRunning: t.longRunning, openCalls: c.openCalls,
  };
}

/* ---- URL parameters: kind, country, view, month ---- */

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
const MONTH_RE = /^(\d{4})-(0[1-9]|1[0-2])$/;

export interface CalendarParams {
  kind: KindFilter; countries: string[]; view: CalendarView; month: string | null;
  /** WP-87: the tender list's filters (search, CPV, scope, defence goods, deadline and value range), as /tenders reads them. */
  tender: Pick<TenderFilters, 'q' | 'cpv' | 'cpvMain' | 'notCpv' | 'scope' | 'goods' | 'deadlineFrom' | 'deadlineTo' | 'valueMin' | 'valueMax' | 'currency'>;
  /** 1-based page of the list view. */
  page: number;
  /** A `month` that is not YYYY-MM, as sent: it is ignored and the page says so. */
  badMonth: string | null;
}

export function parseCalendarParams(sp: SearchParams): CalendarParams {
  const kind = first(sp.kind);
  const raw = (Array.isArray(sp.country) ? sp.country : [sp.country ?? '']).flatMap((s) => s.split(','));
  const countries = [...new Set(raw.map((s) => s.trim().toUpperCase()).filter((s) => /^[A-Z]{2}$/.test(s)))].slice(0, 20);
  const month = first(sp.month);
  const page = Math.floor(Number(first(sp.page)));
  const t = parseTenderFilters(sp);
  const tender: CalendarParams['tender'] = {};
  if (t.q) tender.q = t.q;
  if (t.cpv) tender.cpv = t.cpv;
  if (t.cpvMain) tender.cpvMain = true;               // WP-90
  if (t.notCpv) tender.notCpv = t.notCpv;
  if (t.scope && t.scope !== DEFAULT_TENDER_SCOPE) tender.scope = t.scope;
  if (t.goods) tender.goods = t.goods;
  if (t.deadlineFrom) tender.deadlineFrom = t.deadlineFrom;
  if (t.deadlineTo) tender.deadlineTo = t.deadlineTo;
  if (t.valueMin !== undefined) tender.valueMin = t.valueMin;
  if (t.valueMax !== undefined) tender.valueMax = t.valueMax;
  if (t.currency) tender.currency = t.currency;
  return {
    tender,
    kind: kind === 'tenders' || kind === 'funding' ? kind : 'all',
    countries,
    view: first(sp.view) === 'month' ? 'month' : 'list',
    month: month && MONTH_RE.test(month) ? month : null,
    page: Number.isFinite(page) && page >= 1 ? Math.min(page, 1000) : 1,
    badMonth: month && !MONTH_RE.test(month) ? month.slice(0, 20) : null,
  };
}

/**
 * The entries a calendar shows for its filters: the kind, the countries, the deadline range (a day, UTC, both ends included, as
 * /tenders reads it). A tender-only filter (WP-87) leaves the funding calls out of "Tenders and funding calls": they cannot match it.
 */
export function filterEntries(entries: CalendarEntry[], f: Pick<CalendarParams, 'kind' | 'countries'> & Partial<Pick<CalendarParams, 'tender'>>): CalendarEntry[] {
  const tenderFilter = tenderOnly(f.tender).length > 0;
  const from = f.tender?.deadlineFrom;
  const to = f.tender?.deadlineTo;
  return entries.filter((e) => {
    if (f.kind === 'tenders' && e.kind !== 'tender') return false;
    if (f.kind === 'funding' && e.kind !== 'funding') return false;
    if (f.kind === 'all' && tenderFilter && e.kind !== 'tender') return false;
    if (f.countries.length > 0 && !(e.country && f.countries.includes(e.country))) return false;
    const day = dayOf(e.deadline);
    if (from && day < from) return false;
    if (to && day > to) return false;
    return true;
  });
}

/** Query string of a calendar link; defaults are left out. The tender filters travel as /tenders writes them (WP-87). */
export function calendarQuery(p: Partial<Omit<CalendarParams, 'badMonth'>>): string {
  const q = new URLSearchParams();
  if (p.kind && p.kind !== 'all') q.set('kind', p.kind);
  if (p.countries?.length) q.set('country', p.countries.join(','));
  if (p.tender) for (const [k, v] of new URLSearchParams(toTenderQuery(p.tender))) q.set(k, v);
  if (p.view === 'month') q.set('view', 'month');
  if (p.month) q.set('month', p.month);
  if (p.page && p.page > 1) q.set('page', String(p.page));
  const s = q.toString();
  return s ? `?${s}` : '';
}

/* ---- Month arithmetic (UTC, weeks start on Monday) ---- */

export const monthOf = (d: Date) => `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;

export function shiftMonth(month: string, by: number): string {
  const m = MONTH_RE.exec(month);
  if (!m) return month;
  return monthOf(new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1 + by, 1)));
}

/** Weeks of the month as `YYYY-MM-DD` keys; days of the neighbouring months are null. */
export function monthWeeks(month: string): (string | null)[][] {
  const m = MONTH_RE.exec(month);
  if (!m) return [];
  const y = Number(m[1]);
  const mo = Number(m[2]) - 1;
  const days = new Date(Date.UTC(y, mo + 1, 0)).getUTCDate();
  const lead = (new Date(Date.UTC(y, mo, 1)).getUTCDay() + 6) % 7;
  const cells: (string | null)[] = [...Array<null>(lead).fill(null)];
  for (let d = 1; d <= days; d++) cells.push(`${month}-${String(d).padStart(2, '0')}`);
  while (cells.length % 7 !== 0) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, i) => cells.slice(i * 7, i * 7 + 7));
}

export function groupByDay(entries: CalendarEntry[]): { day: string; items: CalendarEntry[] }[] {
  const out: { day: string; items: CalendarEntry[] }[] = [];
  for (const e of entries) {
    const day = dayOf(e.deadline);
    const last = out[out.length - 1];
    if (last && last.day === day) last.items.push(e);
    else out.push({ day, items: [e] });
  }
  return out;
}

export { dayOf };

export { pageOf, resolveMonth, truncateTitle } from './calendar-view';
export { tenderOnly };

/** WP-87: the calendar of a tender list's result: its filters (the status, the sort and the page are the list's, not the calendar's). */
export function calendarHrefFor(f: TenderFilters): string {
  const { country, status: _s, sort: _o, page: _p, pageSize: _z, buyer: _b, ...tender } = f;
  return `/calendar${calendarQuery({ kind: 'tenders', countries: country ?? [], tender })}`;
}
