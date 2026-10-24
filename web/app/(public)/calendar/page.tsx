import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { CalendarDays, CalendarPlus, ChevronLeft, ChevronRight, Download, List } from 'lucide-react';
import { now } from '@/lib/deadline';
import { formatMonthUtc, formatNumber, plural } from '@/lib/format';
import {
  calendarQuery, dayOf, filterEntries, loadCalendar, monthOf, pageOf, parseCalendarParams, resolveMonth, shiftMonth,
  type CalendarParams, type KindFilter,
} from '@/lib/calendar';
import { pageOfDay } from '@/lib/calendar-tenders';
import { calendarCounts, calendarNotices, feedLine } from '@/lib/calendar-counts';
import { toTenderQuery, type SearchParams } from '@/lib/filters';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { BUYER_COUNTRY_CODES, countryName } from '@/lib/taxonomy';
import { cn } from '@/lib/utils';
import { EmptyState } from '@/components/dg/feedback';
import { PageHeader } from '@/components/dg/page-header';
import { Choice, Fieldset, TextInput } from '@/components/dg/form';
import { Button } from '@/components/dg/button';
import { Icon } from '@/components/dg/icon';
import { FilterNotices } from '@/components/dg/filter-notices';
import { Pagination } from '@/components/dg/pagination';
import { FilterPanel } from '@/components/funding/filter-panel';
import { Agenda, MonthGrid } from '@/components/calendar/calendar-views';

export const revalidate = 60;

/** Entries per page of the agenda, in the list and in the month view. 50, not 100 (WP-63): the page is about half the bytes, so it
 * arrives sooner and a browser has less inline page data to wait for while it hydrates (the race behind React error #418, WP-54). */
const LIST_PAGE = 50;
const MONTHS_AHEAD = 24;
const KINDS: { value: KindFilter; label: string }[] = [
  { value: 'all', label: 'Tenders and funding calls' },
  { value: 'tenders', label: 'Tenders' },
  { value: 'funding', label: 'Funding calls' },
];
const FORM = 'flex flex-col gap-6 rounded-lg border border-transparent bg-surface p-5';

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const p = parseCalendarParams(await searchParams);
  return buildMetadata({
    title: 'Deadline calendar: defence tenders and calls',
    description: 'Upcoming deadlines of open defence tenders and funding calls in one calendar, in UTC, each linked to its record. Also as an iCalendar feed.',
    path: '/calendar',
    // Filtered and month views share the canonical page and stay out of the index.
    noindex: p.kind !== 'all' || p.countries.length > 0 || p.view !== 'list' || p.month !== null || p.page > 1 || Object.keys(p.tender).length > 0,
  });
}

export default async function CalendarPage({ searchParams }: Props) {
  const sp = await searchParams;
  const p = parseCalendarParams(sp);
  const data = await loadCalendar(undefined, { ...p.tender, country: p.countries.length > 0 ? p.countries : undefined });
  // Neither service answered: nothing to show, so the page fails (a 503 at the edge, re-audit N2) and error.tsx says so.
  // One of the two down still renders the other, with a line that says which is missing.
  if (!data.tendersOk && !data.callsOk) throw new Error('calendar: the tender and funding services did not answer');
  const ref = now();
  const today = ref.toISOString().slice(0, 10);
  const current = monthOf(ref);
  const last = shiftMonth(current, MONTHS_AHEAD);
  // A month outside the window the data covers is clamped to it, and the page says so.
  const { month, clamped } = resolveMonth(p.month, current, last);

  // WP-106 (p09): every country a notice or a call can have, not only those of the entries in view (a country filter narrowed the
  // list to the three chosen, and no other could be added)
  const countries = [...new Set([...BUYER_COUNTRY_CODES, ...data.entries.map((e) => e.country), ...p.countries].filter((c): c is string => Boolean(c)))].sort();
  const entries = filterEntries(data.entries, p);
  const inMonth = entries.filter((e) => dayOf(e.deadline).startsWith(month));
  // Both views list their entries a page at a time (50): a month of 593 tenders is twelve pages, not one page of 600 cards.
  const listed = p.view === 'month' ? inMonth : entries;
  const paged = pageOf(listed, p.page, LIST_PAGE);
  if (p.page > paged.pages) redirect(`/calendar${calendarQuery({ ...p, month: p.view === 'month' ? month : null, page: paged.pages })}`);
  const shown = paged.items;
  const total = listed.length;
  const firstShown = (paged.page - 1) * LIST_PAGE + 1;
  const Count = total === 0 ? 'p' : 'h2';
  const notices = [
    // WP-87: a parameter the calendar does not read, or a tender filter a funding call cannot match, is said
    ...calendarNotices(sp, p),
    ...(p.badMonth ? [`Ignored filter: month=${p.badMonth} (use YYYY-MM)`] : []),
    // QA m-10: the list view reads no month; it used to drop one silently
    ...(p.view !== 'month' && p.month ? [`Ignored filter: month=${p.month} (only the month view reads it; add view=month)`] : []),
    ...(p.view === 'month' && clamped && p.month
      ? [`The calendar covers ${formatMonthUtc(`${current}-01T00:00:00Z`)} to ${formatMonthUtc(`${last}-01T00:00:00Z`)}. ${formatMonthUtc(`${p.month}-01T00:00:00Z`)} is outside it, so ${formatMonthUtc(`${month}-01T00:00:00Z`)} is shown.`]
      : []),
  ];

  const href = (over: Partial<CalendarParams>) => `/calendar${calendarQuery({ ...p, page: 1, month: p.view === 'month' ? month : null, ...over })}`;
  const feed = `/calendar.ics${calendarQuery({ kind: p.kind, countries: p.countries, tender: p.tender })}`;
  const counts = calendarCounts(data, p, {
    tenders: filterEntries(data.entries, { ...p, kind: 'tenders' }).length,
    calls: filterEntries(data.entries, { ...p, kind: 'funding' }).length,
  }, today);
  const feedEvents = filterEntries([...data.entries, ...data.upcoming], p).length;
  // WP-100: the feed's events beyond the deadlines listed here, said in the same line (1,503 events beside 1,457 deadlines)
  const feedOpenings = filterEntries(data.upcoming, p).length;
  // The same address for a calendar app that subscribes: `webcal://` opens it there instead of downloading a file.
  const subscribe = absoluteUrl(feed).replace(/^https?:/, 'webcal:');

  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', href: '/' }, { label: 'Deadline calendar', href: '/calendar' }]} title="Deadline calendar"
        lead="The deadlines of open defence tenders and funding calls, soonest first, each linked to its record and source; times in UTC, or the date alone where only a date is given." />

      <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <FilterPanel activeCount={(p.kind !== 'all' ? 1 : 0) + (p.countries.length > 0 ? 1 : 0) + Object.keys(p.tender).length}>
            <form method="get" action="/calendar" role="search" aria-label="Filter the calendar" className={FORM}>
              <Fieldset legend="Show">
                {KINDS.map((k) => <Choice key={k.value} type="radio" name="kind" value={k.value} label={k.label} defaultChecked={p.kind === k.value} />)}
              </Fieldset>
              {countries.length > 0 && (
                <Fieldset legend="Country">
                  {countries.map((c) => (
                    <Choice key={c} name="country" value={c} defaultChecked={p.countries.includes(c)}
                      label={<span className="inline-flex gap-2"><span className="font-mono text-mono-strong">{c}</span>{countryName(c)}</span>} />
                  ))}
                </Fieldset>
              )}
              {/* WP-106 (p04): the product code, on the calendar itself (it worked only through the link from /tenders) */}
              <TextInput name="cpv" maxLength={200} label="CPV code (tenders)" placeholder="For example 353, 2461" defaultValue={p.tender.cpv?.join(', ') ?? ''}
                hint="Funding calls have no code: with one, only tenders are listed." />
              {/* The tender list's other filters this calendar came with travel with the form (WP-87). */}
              {[...new URLSearchParams(toTenderQuery({ ...p.tender, cpv: undefined, cpvMain: undefined }))].map(([k, v]) => <input key={k} type="hidden" name={k} value={v} />)}
              {p.tender.cpvMain && <input type="hidden" name="cpvMain" value="true" />}
              {p.view === 'month' && <input type="hidden" name="view" value="month" />}
              {p.view === 'month' && <input type="hidden" name="month" value={month} />}
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit">Apply filters</Button>
                <Link href="/calendar" className="inline-flex min-h-11 items-center text-small font-bold">Clear all</Link>
              </div>
            </form>
          </FilterPanel>

          <section aria-labelledby="feed-heading" className="flex flex-col gap-2 rounded-lg border border-transparent bg-surface p-5">
            <h2 id="feed-heading" className="m-0 text-h3">Calendar feed</h2>
            <p className="m-0 text-small text-ink-muted">
              Add this address to your calendar app to follow the deadlines this page lists, and the opening days of funding calls that have not opened, with the filters you chose. {feedLine(feedEvents, 5000, feedOpenings)} Times are UTC. The feed is refreshed hourly from data collected once a day.
            </p>
            <a href={subscribe} className="inline-flex min-h-11 items-center gap-2 text-small font-bold">
              <Icon icon={CalendarPlus} size="inline" />Subscribe in your calendar app
            </a>
            <code className="break-all font-mono text-mono text-ink-muted">{absoluteUrl(feed)}</code>
            <a href={feed} download className="inline-flex min-h-11 items-center gap-2 text-small font-bold">
              <Icon icon={Download} size="inline" />Download .ics
            </a>
            <details className="text-small text-ink-muted">
              <summary className="min-h-11 cursor-pointer py-2 font-bold text-ink">If the subscribe link does nothing</summary>
              <ul className="m-0 flex list-none flex-col gap-1 p-0 pt-1">
                <li><span className="font-semibold text-ink">Google Calendar:</span> Other calendars, From URL, paste the address above.</li>
                <li><span className="font-semibold text-ink">Outlook:</span> Add calendar, Subscribe from web, paste the address.</li>
                <li><span className="font-semibold text-ink">Apple Calendar:</span> File, New Calendar Subscription, paste the address.</li>
              </ul>
            </details>
          </section>
        </div>

        <section aria-labelledby="results-heading" className="flex min-w-0 flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* An empty result has one heading, the empty state's. */}
            <Count id="results-heading" className="m-0 mr-auto text-body font-semibold" aria-live="polite">
              {total === 0 ? 'No deadlines' : p.view === 'month' ? `${formatNumber(total)} ${total === 1 ? 'deadline' : 'deadlines'} in ${formatMonthUtc(`${month}-01T00:00:00Z`)}` : `${formatNumber(total)} upcoming ${total === 1 ? 'deadline' : 'deadlines'}`}
            </Count>
            <div role="group" aria-label="View" className="flex rounded-pill bg-surface p-1">
              {(['list', 'month'] as const).map((v) => (
                <Link key={v} href={href({ view: v, month: v === 'month' ? month : null })} aria-current={p.view === v ? 'true' : undefined}
                  className={cn('inline-flex min-h-9 items-center gap-1.5 rounded-pill px-3 text-small font-bold no-underline hover:no-underline',
                    p.view === v ? 'bg-primary text-on-primary' : 'text-ink hover:bg-surface-inset')}>
                  <Icon icon={v === 'list' ? List : CalendarDays} size="inline" />{v === 'list' ? 'List' : 'Month'}
                </Link>
              ))}
            </div>
          </div>

          {counts.length > 0 && (
            <div className="flex flex-col gap-1 text-small text-ink-muted" data-calendar-counts>
              {counts.map((c) => <p key={c.key} className="m-0">{c.text}{c.href && <> <Link href={c.href} className="font-semibold">{c.link}</Link>.</>}</p>)}
            </div>
          )}
          {p.view === 'month' && (
            <nav aria-label="Month" className="flex flex-wrap items-center justify-between gap-2">
              {month > current
                ? <Link href={href({ month: shiftMonth(month, -1) })} className="inline-flex min-h-11 items-center gap-1 text-small font-bold"><Icon icon={ChevronLeft} size="inline" />{formatMonthUtc(`${shiftMonth(month, -1)}-01T00:00:00Z`)}</Link>
                : <span aria-hidden="true" />}
              <span className="font-mono text-mono-strong">{formatMonthUtc(`${month}-01T00:00:00Z`)}</span>
              {month < last
                ? <Link href={href({ month: shiftMonth(month, 1) })} className="inline-flex min-h-11 items-center gap-1 text-small font-bold">{formatMonthUtc(`${shiftMonth(month, 1)}-01T00:00:00Z`)}<Icon icon={ChevronRight} size="inline" /></Link>
                : <span aria-hidden="true" />}
            </nav>
          )}

            <>
              <FilterNotices notices={notices} />
              {(!data.tendersOk || !data.callsOk) && (
                <p role="status" className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-small text-ink">
                  {!data.tendersOk ? 'Tenders could not be loaded just now; only funding calls are listed.' : 'Funding calls could not be loaded just now; only tenders are listed.'}
                </p>
              )}
              {p.view === 'month' && (
                <MonthGrid month={month} label={formatMonthUtc(`${month}-01T00:00:00Z`)} entries={inMonth} today={today}
                  moreHref={(day) => `${href({ page: pageOfDay(inMonth, day, LIST_PAGE) })}#d-${day}`} />
              )}
              {total === 0 ? (
                <EmptyState title={p.view === 'month' ? 'No deadlines in this month' : 'No upcoming deadlines match'}
                  action={<Button variant="secondary" href="/calendar">Clear filters</Button>}>
                  {p.view === 'month' ? 'Try another month, or show tenders and funding calls together.' : 'Try showing tenders and funding calls together, or fewer countries.'}
                </EmptyState>
              ) : (
                <Agenda entries={shown} />
              )}
              {total > LIST_PAGE && (
                <>
                  <p className="m-0 text-small text-ink-muted">
                    Showing {formatNumber(firstShown)}–{formatNumber(firstShown + shown.length - 1)} of {formatNumber(total)} {plural(total, 'deadline')}{p.view === 'month' ? ' in this month' : ''}.
                  </p>
                  <Pagination page={paged.page} total={total} pageSize={LIST_PAGE} hrefFor={(n) => href({ page: n })} />
                </>
              )}
            </>

          <p className="m-0 max-w-prose text-small text-ink-muted">
            Open tenders in the defence scope and open funding calls with a stated deadline. Calls that have not opened yet and entries without a deadline are not listed here; the calendar feed has the opening days of the calls that have not opened.
            {data.tendersOk && data.tendersTotal > data.tendersHeld && (
              <> The calendar holds the {data.tendersHeld} open tenders with the earliest deadlines of {data.tendersTotal}; later ones are on the <Link href="/tenders" className="font-semibold">tenders list</Link>.</>
            )}
            {' '}Check the original notice before you act: it is authoritative.
          </p>
        </section>
      </div>
    </>
  );
}
