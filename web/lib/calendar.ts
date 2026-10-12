/**
 * Data of the deadline calendar (/calendar and /calendar.ics): the open defence tenders and the open funding
 * calls that have a deadline, from the public API helpers only. Nothing is converted or invented: an entry is
 * the notice's own deadline.
 */
import { getCalls, getTenders, isCallSlug, isTenderSlug } from './api';
import { getCallDeadline, getTenderDeadline, now } from './deadline';
import { anomalyNotes, tenderStatusView } from './tender-status';
import type { SearchParams } from './filters';

export type CalendarKind = 'tender' | 'funding';
export type KindFilter = 'all' | 'tenders' | 'funding';
export type CalendarView = 'list' | 'month';

export interface CalendarEntry {
  /** `<kind>-<id>`: also the stable part of the calendar-file UID. */
  key: string;
  kind: CalendarKind;
  id: string;
  title: string;
  /** Site path of the detail page. */
  href: string;
  /** ISO UTC. */
  deadline: string;
  /** The source gives a date, not a time of day. */
  dateOnly: boolean;
  /** "13 Oct 2026, UTC" or "13 Oct 2026, 16:00 UTC". */
  when: string;
  /** The buyer, or the funder of a call. */
  who: string;
  /** ISO-2 of the buyer; the funder country (or EU) of a call. */
  country: string | null;
  sourceName: string;
  /** A known anomaly of the source's dates, in words. */
  note: string | null;
}

export interface CalendarData {
  entries: CalendarEntry[];
  tendersOk: boolean;
  callsOk: boolean;
  /** Open tenders in total, and how many the calendar holds (the earliest deadlines first). */
  tendersTotal: number;
  tendersHeld: number;
}

const TENDER_PAGE = 100;
const TENDER_PAGES = 5;
const CALL_PAGE = 500;

const dayOf = (iso: string) => new Date(iso).toISOString().slice(0, 10);

async function loadTenders(ref: Date): Promise<{ entries: CalendarEntry[]; total: number; held: number }> {
  const base = { status: 'open', scope: 'core', sort: 'deadline-asc', pageSize: TENDER_PAGE } as const;
  const first = await getTenders({ ...base, page: 1 }, { cacheable: true });
  const items = [...first.items];
  const size = Math.max(1, first.pageSize || TENDER_PAGE);
  const pages = Math.min(TENDER_PAGES, Math.ceil(first.total / size));
  if (pages > 1) {
    const rest = await Promise.all(
      Array.from({ length: pages - 1 }, (_, i) => getTenders({ ...base, page: i + 2 }, { cacheable: true })),
    );
    for (const r of rest) items.push(...r.items);
  }
  const entries: CalendarEntry[] = [];
  for (const t of items) {
    const view = tenderStatusView(t, ref);
    if (view.kind !== 'open' && view.kind !== 'soon') continue;
    const d = getTenderDeadline(t, ref);
    if (!d.iso || d.state === 'closed' || !isTenderSlug(t.slug)) continue;
    entries.push({
      key: `tender-${t.id}`, kind: 'tender', id: t.id, title: t.title, href: `/tenders/${t.slug}`,
      deadline: d.iso, dateOnly: d.dateOnly === true, when: d.utc,
      who: t.buyerName, country: t.country, sourceName: t.source.sourceName, note: anomalyNotes(t)[0] ?? null,
    });
  }
  return { entries, total: first.total, held: items.length };
}

async function loadCalls(ref: Date): Promise<CalendarEntry[]> {
  const r = await getCalls({ status: 'open', pageSize: CALL_PAGE, page: 1 }, { cacheable: true });
  const entries: CalendarEntry[] = [];
  for (const c of r.items) {
    const d = getCallDeadline(c, ref);
    // A rolling call past its last cut-off is open but has no coming deadline to put on a calendar.
    if (c.status !== 'open' || !c.deadline || !d.iso || d.state === 'closed' || d.rolling || !isCallSlug(c.slug)) continue;
    entries.push({
      key: `funding-${c.id}`, kind: 'funding', id: c.id, title: c.title, href: `/funding/${c.slug}`,
      deadline: c.deadline, dateOnly: d.dateOnly === true, when: d.utc,
      who: c.issuer ?? c.programmeName, country: c.funderCountry, sourceName: c.source.sourceName, note: null,
    });
  }
  return entries;
}

/** Tenders and calls together, soonest deadline first. A failing half is reported, not hidden. */
export async function loadCalendar(ref: Date = now()): Promise<CalendarData> {
  const [t, c] = await Promise.all([
    loadTenders(ref).then((v) => ({ ok: true as const, ...v })).catch(() => ({ ok: false as const, entries: [] as CalendarEntry[], total: 0, held: 0 })),
    loadCalls(ref).then((v) => ({ ok: true as const, entries: v })).catch(() => ({ ok: false as const, entries: [] as CalendarEntry[] })),
  ]);
  const entries = [...t.entries, ...c.entries].sort((a, b) => new Date(a.deadline).getTime() - new Date(b.deadline).getTime() || a.key.localeCompare(b.key));
  return { entries, tendersOk: t.ok, callsOk: c.ok, tendersTotal: t.total, tendersHeld: t.held };
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
