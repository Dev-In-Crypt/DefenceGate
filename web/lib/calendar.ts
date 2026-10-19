/**
 * Data of the deadline calendar (/calendar and /calendar.ics): the open defence tenders and the open funding
 * calls that have a deadline, from the public API helpers only. Nothing is converted or invented: an entry is
 * the notice's own deadline.
 */
import { getCalls, getTenderCalendar, isCallSlug, isTenderSlug } from './api';
import { entryFromItem, type CalendarEntry } from './calendar-tenders';
import { getCallDeadline, now } from './deadline';
import { formatDateLabelledUtc } from './format';
import { ROLLING_NOTE } from './ics';
import type { SearchParams } from './filters';

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
}

const CALL_PAGE = 500;

const dayOf = (iso: string) => new Date(iso).toISOString().slice(0, 10);

/**
 * The open tenders with a deadline, all of them in one read (GET /v1/tenders/calendar). The calendar used to read five
 * pages of the list, the 500 earliest of 1,529, and November showed none of its 593 (UX audit T9).
 */
async function loadTenders(ref: Date): Promise<{ entries: CalendarEntry[]; total: number; held: number; longRunning: number }> {
  const page = await getTenderCalendar();
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

async function loadCalls(ref: Date): Promise<{ entries: CalendarEntry[]; upcoming: CalendarEntry[] }> {
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
  return { entries, upcoming };
}

const byTime = (a: CalendarEntry, b: CalendarEntry) => new Date(a.deadline).getTime() - new Date(b.deadline).getTime() || a.key.localeCompare(b.key);

/** Tenders and calls together, soonest deadline first. A failing half is reported, not hidden. */
export async function loadCalendar(ref: Date = now()): Promise<CalendarData> {
  const [t, c] = await Promise.all([
    loadTenders(ref).then((v) => ({ ok: true as const, ...v })).catch(() => ({ ok: false as const, entries: [] as CalendarEntry[], total: 0, held: 0, longRunning: 0 })),
    loadCalls(ref).then((v) => ({ ok: true as const, ...v })).catch(() => ({ ok: false as const, entries: [] as CalendarEntry[], upcoming: [] as CalendarEntry[] })),
  ]);
  const entries = [...t.entries, ...c.entries].sort(byTime);
  return { entries, upcoming: c.upcoming.sort(byTime), tendersOk: t.ok, callsOk: c.ok, tendersTotal: t.total, tendersHeld: t.held, longRunning: t.longRunning };
}

/* ---- URL parameters: kind, country, view, month ---- */

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
const MONTH_RE = /^(\d{4})-(0[1-9]|1[0-2])$/;

export interface CalendarParams {
  kind: KindFilter; countries: string[]; view: CalendarView; month: string | null;
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
  return {
    kind: kind === 'tenders' || kind === 'funding' ? kind : 'all',
    countries,
    view: first(sp.view) === 'month' ? 'month' : 'list',
    month: month && MONTH_RE.test(month) ? month : null,
    page: Number.isFinite(page) && page >= 1 ? Math.min(page, 1000) : 1,
    badMonth: month && !MONTH_RE.test(month) ? month.slice(0, 20) : null,
  };
}

export function filterEntries(entries: CalendarEntry[], f: Pick<CalendarParams, 'kind' | 'countries'>): CalendarEntry[] {
  return entries.filter((e) => {
    if (f.kind === 'tenders' && e.kind !== 'tender') return false;
    if (f.kind === 'funding' && e.kind !== 'funding') return false;
    if (f.countries.length > 0 && !(e.country && f.countries.includes(e.country))) return false;
    return true;
  });
}

/** Query string of a calendar link; defaults are left out. */
export function calendarQuery(p: Partial<Omit<CalendarParams, 'badMonth'>>): string {
  const q = new URLSearchParams();
  if (p.kind && p.kind !== 'all') q.set('kind', p.kind);
  if (p.countries?.length) q.set('country', p.countries.join(','));
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
