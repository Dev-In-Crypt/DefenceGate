import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { CalendarDays, ChevronLeft, ChevronRight, Download, List } from 'lucide-react';
import { now } from '@/lib/deadline';
import { formatMonthUtc } from '@/lib/format';
import {
  calendarQuery, dayOf, filterEntries, loadCalendar, monthOf, pageOf, parseCalendarParams, resolveMonth, shiftMonth,
  type CalendarParams, type KindFilter,
} from '@/lib/calendar';
import type { SearchParams } from '@/lib/filters';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { countryName } from '@/lib/taxonomy';
import { cn } from '@/lib/utils';
import { Breadcrumbs, EmptyState, ErrorState } from '@/components/dg/feedback';
import { Choice, Fieldset } from '@/components/dg/form';
import { Button } from '@/components/dg/button';
import { Icon } from '@/components/dg/icon';
import { FilterNotices } from '@/components/dg/filter-notices';
import { Pagination } from '@/components/dg/pagination';
import { FilterPanel } from '@/components/funding/filter-panel';
import { Agenda, MonthGrid } from '@/components/calendar/calendar-views';

export const revalidate = 3600;

/** Entries per page of the list view; the month view lists a month's entries up to MONTH_CAP. */
const LIST_PAGE = 100;
const MONTH_CAP = 300;
const MONTHS_AHEAD = 24;
const KINDS: { value: KindFilter; label: string }[] = [
  { value: 'all', label: 'Tenders and funding calls' },
  { value: 'tenders', label: 'Tenders' },
  { value: 'funding', label: 'Funding calls' },
];
const FORM = 'flex flex-col gap-6 rounded-lg bg-surface p-5';

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const p = parseCalendarParams(await searchParams);
  return buildMetadata({
    title: 'Deadline calendar for defence tenders and funding calls',
    description: 'Upcoming deadlines of open defence tenders and funding calls in one calendar, in UTC, each linked to its record. Also as an iCalendar feed.',
    path: '/calendar',
    // Filtered and month views share the canonical page and stay out of the index.
    noindex: p.kind !== 'all' || p.countries.length > 0 || p.view !== 'list' || p.month !== null || p.page > 1,
  });
}

export default async function CalendarPage({ searchParams }: Props) {
  const p = parseCalendarParams(await searchParams);
  const data = await loadCalendar();
  const ref = now();
  const today = ref.toISOString().slice(0, 10);
  const current = monthOf(ref);
  const last = shiftMonth(current, MONTHS_AHEAD);
  // A month outside the window the data covers is clamped to it, and the page says so.
  const { month, clamped } = resolveMonth(p.month, current, last);

  const countries = [...new Set([...data.entries.map((e) => e.country), ...p.countries].filter((c): c is string => Boolean(c)))].sort();
  const entries = filterEntries(data.entries, p);
  const inMonth = entries.filter((e) => dayOf(e.deadline).startsWith(month));
  const paged = pageOf(entries, p.page, LIST_PAGE);
  if (p.view === 'list' && p.page > paged.pages) redirect(`/calendar${calendarQuery({ ...p, page: paged.pages })}`);
  const shown = p.view === 'month' ? inMonth.slice(0, MONTH_CAP) : paged.items;
  const total = p.view === 'month' ? inMonth.length : entries.length;
  const firstShown = (paged.page - 1) * LIST_PAGE + 1;
  const Count = total === 0 ? 'p' : 'h2';
  const notices = [
    ...(p.badMonth ? [`Ignored filter: month=${p.badMonth} (use YYYY-MM)`] : []),
    ...(p.view === 'month' && clamped && p.month
      ? [`The calendar covers ${formatMonthUtc(`${current}-01T00:00:00Z`)} to ${formatMonthUtc(`${last}-01T00:00:00Z`)}. ${formatMonthUtc(`${p.month}-01T00:00:00Z`)} is outside it, so ${formatMonthUtc(`${month}-01T00:00:00Z`)} is shown.`]
      : []),
  ];

  const href = (over: Partial<CalendarParams>) => `/calendar${calendarQuery({ ...p, page: 1, month: p.view === 'month' ? month : null, ...over })}`;
  const feed = `/calendar.ics${calendarQuery({ kind: p.kind, countries: p.countries })}`;
  const bothDown = !data.tendersOk && !data.callsOk;

  return (
    <>
      <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: 'Deadline calendar', href: '/calendar' }]} />
      <header className="flex flex-col gap-3">
        <h1 className="m-0 text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1">Deadline calendar</h1>
        <p className="m-0 max-w-[62ch] text-body text-ink-muted">
          The deadlines of open defence tenders and open funding calls, soonest first. Times are UTC; a notice that gives only a date shows only the date. Each entry links to its record and its source.
        </p>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <FilterPanel activeCount={(p.kind !== 'all' ? 1 : 0) + (p.countries.length > 0 ? 1 : 0)}>
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
              {p.view === 'month' && <input type="hidden" name="view" value="month" />}
              {p.view === 'month' && <input type="hidden" name="month" value={month} />}
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit">Apply filters</Button>
                <Link href="/calendar" className="inline-flex min-h-11 items-center text-small font-bold">Clear all</Link>
              </div>
            </form>
          </FilterPanel>

          <section aria-labelledby="feed-heading" className="flex flex-col gap-2 rounded-lg bg-surface p-5">
            <h2 id="feed-heading" className="m-0 text-body font-bold">Calendar feed</h2>
            <p className="m-0 text-small text-ink-muted">
              Add this address to your calendar app to follow the deadlines above. Up to 500 events, in UTC, refreshed hourly.
            </p>
            <code className="break-all rounded-md bg-surface-inset px-3 py-2 font-mono text-mono">{absoluteUrl(feed)}</code>
            <a href={feed} download className="inline-flex min-h-11 items-center gap-2 text-small font-bold">
              <Icon icon={Download} size="inline" />Download .ics
            </a>
          </section>
        </div>

        <section aria-labelledby="results-heading" className="flex min-w-0 flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* An empty result has one heading, the empty state's. */}
            <Count id="results-heading" className="m-0 mr-auto text-body font-semibold" aria-live="polite">
              {total === 0 ? 'No deadlines' : p.view === 'month' ? `${total} ${total === 1 ? 'deadline' : 'deadlines'} in ${formatMonthUtc(`${month}-01T00:00:00Z`)}` : `${total} upcoming ${total === 1 ? 'deadline' : 'deadlines'}`}
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

          {bothDown ? (
            <ErrorState retryHref="/calendar">The tender and funding services did not answer. Try again in a few minutes.</ErrorState>
          ) : (
            <>
              <FilterNotices notices={notices} />
              {(!data.tendersOk || !data.callsOk) && (
                <p role="status" className="m-0 rounded-md bg-surface-inset px-4 py-3 text-small text-ink">
                  {!data.tendersOk ? 'Tenders could not be loaded just now; only funding calls are listed.' : 'Funding calls could not be loaded just now; only tenders are listed.'}
                </p>
              )}
              {p.view === 'month' && <MonthGrid month={month} label={formatMonthUtc(`${month}-01T00:00:00Z`)} entries={inMonth} today={today} />}
              {total === 0 ? (
                <EmptyState title={p.view === 'month' ? 'No deadlines in this month' : 'No upcoming deadlines match'}
                  action={<Button variant="secondary" href="/calendar">Clear filters</Button>}>
                  {p.view === 'month' ? 'Try another month, or show tenders and funding calls together.' : 'Try showing tenders and funding calls together, or fewer countries.'}
                </EmptyState>
              ) : (
                <Agenda entries={shown} />
              )}
              {p.view === 'month' && total > shown.length && (
                <p className="m-0 text-small text-ink-muted">
                  Showing the first {shown.length} of {total}. Narrow the filters to see the rest.
                </p>
              )}
              {p.view === 'list' && total > LIST_PAGE && (
                <>
                  <p className="m-0 text-small text-ink-muted">
                    Showing {firstShown}–{firstShown + shown.length - 1} of {total} deadlines.
                  </p>
                  <Pagination page={paged.page} total={total} pageSize={LIST_PAGE} hrefFor={(n) => href({ page: n })} />
                </>
              )}
            </>
          )}

          <p className="m-0 text-small text-ink-muted">
            Open tenders in the defence scope and open funding calls with a stated deadline. Calls that have not opened yet and entries without a deadline are not listed.
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
