import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';
import { Rss } from 'lucide-react';
import { getChanges, getDigestWeeks } from '@/lib/api';
import { weekLabel, weekOf, weekSoFarLabel } from '@/lib/digest';
import { now } from '@/lib/deadline';
import { CHANGE_MAX_PAGE, MAX_QUERY_LENGTH, ignoredFilters, lastPage, parseChangeFilters, toChangeQuery, toTenderQuery, PARAM, type SearchParams } from '@/lib/filters';
import { formatDateTimeUtc, formatDateUtc, formatNumber, plural } from '@/lib/format';
import { staleNote } from '@/lib/source-status';
import { BUYER_COUNTRIES, SCOPE_CHOICES } from '@/lib/taxonomy';
import { NOT_FOUND_META, buildMetadata } from '@/lib/seo';
import type { Change, ChangeKindFilter } from '@/lib/types';
import { AutoGrid } from '@/components/dg/auto-grid';
import { Button } from '@/components/dg/button';
import { EmptyState } from '@/components/dg/feedback';
import { AboutData } from '@/components/dg/about-data';
import { FilterNotices } from '@/components/dg/filter-notices';
import { PageHeader } from '@/components/dg/page-header';
import { Select, TextInput } from '@/components/dg/form';
import { Icon } from '@/components/dg/icon';
import { Pagination } from '@/components/dg/pagination';
import { Tag } from '@/components/dg/tag';
import { ChangeEntry, FIRST_COLLECTED, FIRST_COLLECTED_AWARD } from '@/components/changes/change-entry';
import { FundingChangeEntry } from '@/components/changes/funding-change-entry';
import { FitFilter, FitItem } from '@/components/funding/fit-badge';

export const revalidate = 60;

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseChangeFilters(await searchParams);
  // WP-116: a week the archive does not have is the page's 404 (below), and the tab says so too (one row is asked; an outage
  // is not taken for a missing week here)
  if (f.week && await getChanges({ week: f.week, pageSize: 1 }).then((d) => d === null, () => false)) return NOT_FOUND_META;
  const meta = buildMetadata({
    title: 'What changed in the last 14 days',
    description: 'New defence and dual-use notices and the amendments to their deadline, value, status or procedure, taken from our archive of observed changes. With an Atom feed.',
    path: '/changes',
    noindex: toChangeQuery({ ...f, pageSize: undefined }) !== '',
  });
  return { ...meta, alternates: { ...meta.alternates, types: { 'application/atom+xml': '/changes.atom' } } };
}

/** WP-90: the kinds of change a list can be narrowed to (the API's `kind`), and how a sentence names them. */
const KIND_WORDS: Record<ChangeKindFilter, string> = {
  new: 'the new notices', award: 'the new award notices', amended: 'the amendments', deadline: 'the amendments that moved a deadline',
  value: 'the amendments that changed a value', status: 'the amendments that changed a status',
};
const KIND_OPTIONS = ([['new', 'New notices'], ['award', 'New award notices'], ['amended', 'Every amendment'], ['deadline', 'Deadline moved'], ['value', 'Value changed'], ['status', 'Status changed']] as const)
  .map(([value, label]) => ({ value, label }));

/** The same names as the tender list (lib/taxonomy.ts SCOPE_CHOICES); the default is left unselected. */
const SCOPE_OPTIONS = (['core', 'supply', 'all'] as const).map((value) => ({ value, label: SCOPE_CHOICES[value].label }));

/** The entries of one UTC day, in the API's order (newest first), under that day. */
function byDay(items: Change[]): { day: string; items: Change[] }[] {
  const groups: { day: string; items: Change[] }[] = [];
  for (const c of items) {
    const last = groups.at(-1);
    if (last && last.day === c.day) last.items.push(c);
    else groups.push({ day: c.day, items: [c] });
  }
  return groups;
}

export default async function ChangesPage({ searchParams }: Props) {
  const sp = await searchParams;
  const filters = parseChangeFilters(sp);
  const notices = ignoredFilters(sp, 'changes');
  // WP-90: the week under way ("this week so far", from the digest) is listed up to now; it has no issue of the digest yet
  const thisWeek = filters.week !== undefined && filters.week === weekOf(now());
  // A page past the API's last (100) is past the end of the list: an answer, not an outage (QA m-8)
  const pastEnd = (filters.page ?? 1) > CHANGE_MAX_PAGE;
  // WP-106 (p03): a period beyond the last 14 days: the archive's weeks, each the list behind its digest (the week under way too)
  const [data, weeks] = await Promise.all([pastEnd ? null : getChanges(filters).catch(() => null), getDigestWeeks().catch(() => [])]);
  const current = weekOf(now());
  const periods = [{ value: current, label: weekSoFarLabel(current, now()) }, ...weeks.map((w) => ({ value: w.week, label: weekLabel(w.week) }))];
  if (filters.week && !periods.some((o) => o.value === filters.week)) periods.push({ value: filters.week, label: weekLabel(filters.week) });
  const crumbs = [{ label: 'Home', href: '/' }, { label: 'What changed', href: '/changes' }];
  const header = (
    <PageHeader crumbs={crumbs} title="What changed"
      lead={<>
        {filters.week
          ? `New notices and amendments seen ${thisWeek ? 'so far this week' : `in ${weekLabel(filters.week)}`}. An amendment is a deadline, value, status or procedure that moved, with the old and the new value.`
          : 'New notices and amendments seen in the last 14 days: a deadline, value, status or procedure that moved, with the old and the new value.'}
      </>} />
  );
  const country = filters.country?.[0] ?? '';
  const filterForm = (
    <form method="get" action="/changes" role="search" aria-label="Filter changes" className="flex flex-col gap-4 rounded-lg border border-transparent bg-surface p-5 sm:flex-row sm:flex-wrap sm:items-end">
      <Select name={PARAM.country} label="Buyer country" placeholder="All countries" defaultValue={country} className="sm:min-w-56"
        options={Object.entries(BUYER_COUNTRIES).map(([code, name]) => ({ value: code, label: `${name} (${code})` }))} />
      <Select name={PARAM.scope} label="What to include" placeholder={SCOPE_CHOICES.relevant.label} defaultValue={filters.scope ?? ''}
        className="sm:min-w-72" options={SCOPE_OPTIONS} />
      {/* WP-87: the tender list's search and CPV filter, read by the API as the list reads them */}
      <TextInput search name={PARAM.q} maxLength={MAX_QUERY_LENGTH} label="Search" placeholder="Title, buyer or number" defaultValue={filters.q ?? ''} className="sm:min-w-56" />
      <TextInput name={PARAM.cpv} maxLength={200} label="CPV code" placeholder="For example 35" defaultValue={filters.cpv?.join(', ') ?? ''} className="sm:min-w-40" />
      {/* WP-90: one kind of change, where the archive's lines tell it */}
      <Select name="kind" label="Kind of change" placeholder="Every change" defaultValue={filters.kind ?? ''} className="sm:min-w-56" options={KIND_OPTIONS} />
      {/* the list's other filters this page came with (deadline and value range, defence goods) travel with the form */}
      {[...new URLSearchParams(toTenderQuery({
        goods: filters.goods, deadlineFrom: filters.deadlineFrom, deadlineTo: filters.deadlineTo,
        valueMin: filters.valueMin, valueMax: filters.valueMax, currency: filters.currency, notCpv: filters.notCpv,
      }))].map(([k, v]) => <input key={k} type="hidden" name={k} value={v} />)}
      {/* WP-90: a subscription's own filters (main code only, the status) travel too */}
      {filters.cpvMain && <input type="hidden" name={PARAM.cpvMain} value="true" />}
      {filters.status && <input type="hidden" name={PARAM.status} value={filters.status} />}
      <Select name="week" label="Period" placeholder="The last 14 days" defaultValue={filters.week ?? ''} className="sm:min-w-64" options={periods} />

      <div className="flex items-center gap-3">
        <Button type="submit">Apply</Button>
        <Link href="/changes" className="inline-flex min-h-11 items-center text-small font-bold">Clear</Link>
      </div>
    </form>
  );
  const firstPage = (
    <EmptyState title={`There is no page ${filters.page} of this list`}
      action={<Button variant="secondary" href={`/changes${toChangeQuery({ ...filters, page: 1 })}`}>Go to page 1</Button>}>
      The list ends before this page. Page 1 has the newest changes.
    </EmptyState>
  );
  if (pastEnd) return <>{header}<FilterNotices notices={notices} />{filterForm}{firstPage}</>;
  // A week outside the archive, or not yet ended, is a 404 of the API: not a fault of the list.
  if (!data && filters.week) notFound();
  if (!data) {
    // The filters stay (a visitor who picked a country should not start over), and the way out is a retry.
    return (
      <>
        {header}
        <FilterNotices notices={notices} />
        {filterForm}
        <EmptyState title="The change list is not available right now"
          action={<Button variant="secondary" href={`/changes${toChangeQuery(filters)}`}>Try again</Button>}>
          It is read from our archive and the data service did not answer in time. Your filters are kept; try again in a minute.
          Nothing here means there are no changes: the list could not be read.
        </EmptyState>
      </>
    );
  }
  const last = lastPage(data.total, data.pageSize);
  if (data.total > 0 && (filters.page ?? 1) > last) redirect(`/changes${toChangeQuery({ ...filters, page: last })}`);
  if (data.total === 0 && (filters.page ?? 1) > 1) return <>{header}<FilterNotices notices={notices} />{filterForm}{firstPage}</>;
  // WP-87: the feed of exactly this list (every filter but the page; a feed is always the last 14 days)
  const feedHref = `/changes.atom${toChangeQuery({ ...filters, week: undefined, kind: undefined, page: undefined, pageSize: undefined })}`;
  // A rolling window ends now; a week ends at the next Monday 00:00 (exclusive), so its last day is the second before.
  const windowLast = filters.week ? new Date(new Date(data.windowTo).getTime() - 1000).toISOString() : data.windowTo;
  const from = data.total === 0 ? 0 : (data.page - 1) * data.pageSize + 1;
  const to = Math.min(data.total, data.page * data.pageSize);
  return (
    <>
      {header}
      {data.staleAsOf && (
        <p role="status" className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-small text-ink">{staleNote(data.staleAsOf, formatDateTimeUtc)}</p>
      )}

      {/* Text at the left (one measure), the ways to follow the list at the right: the card is filled, not a strip of text in a wide box. */}
      <section aria-labelledby="window" className="grid gap-x-10 gap-y-4 rounded-lg border border-transparent bg-surface p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="flex min-w-0 flex-col gap-3">
          <h2 id="window" className="m-0 text-h3">{filters.week ? (thisWeek ? weekSoFarLabel(filters.week, now()) : weekLabel(filters.week)) : <>The last {data.windowDays} days</>}</h2>
          <p className="m-0 max-w-prose text-body">
            <span className="font-mono tabular-nums">{formatNumber(data.counts.new)}</span> new notices,{' '}
            {/* WP-95: new award notices apart from the new tenders */}
            <span className="font-mono tabular-nums">{formatNumber(data.counts.awards ?? 0)}</span> new award notices and{' '}
            <span className="font-mono tabular-nums">{formatNumber(data.counts.amended)}</span> amendments, from{' '}
            <time dateTime={data.windowFrom}>{formatDateUtc(data.windowFrom)}</time> to{' '}
            <time dateTime={windowLast}>{formatDateUtc(windowLast)}</time> (UTC).
          </p>
          {(filters.week || filters.kind) && (
            <p className="m-0 max-w-prose text-body">
              {filters.kind ? `Only ${KIND_WORDS[filters.kind]} are listed. ` : ''}
              {filters.week && !thisWeek && <>This is the list behind <Link href={`/digest/${filters.week}`} className="font-semibold">the weekly digest of this week</Link>. </>}
              {thisWeek && <>The week is not over: its <Link href="/digest" className="font-semibold">weekly digest</Link> comes after Sunday. </>}
              <Link href="/changes" className="font-semibold">{filters.week ? 'Show the last 14 days' : 'Show all changes'}</Link>
            </p>
          )}
          {(data.fundingTotal ?? 0) > 0 && (
            <p className="m-0 max-w-prose text-body">
              <span className="font-mono tabular-nums">{formatNumber(data.fundingTotal ?? 0)}</span> funding calls are new or had a date moved by the source; they are listed{' '}
              <a href="#funding-heading" className="font-semibold">below</a>, apart from the notices.
            </p>
          )}
          <AboutData summary="How we count">
          <p className="m-0">
            Taken from our own archive, which began in September 2026: an amendment is a change we observed in a source, on the day we saw it, which may be
            later than the day the buyer made it. Our own corrections and re-readings are never listed, nor are changes we only learned of by loading a
            source&rsquo;s older notices (a notice&rsquo;s own page lists those as earlier changes). A notice counts as new only if it was published in these
            days. A notice published in several places is listed once. One entry is one notice on one day.
          </p>
          <p className="m-0">No account is needed: the list’s Atom feed does what an alert would.</p>
          </AboutData>
        </div>
        <nav aria-label="Follow this list" className="flex flex-col lg:border-l lg:border-line lg:pl-6">
          <a href={feedHref} className="inline-flex min-h-11 items-center gap-2 text-small font-bold">
            <Icon icon={Rss} size="inline" />Atom feed of this list
          </a>
          <Link href="/calendar" className="inline-flex min-h-11 items-center text-small font-bold">Deadline calendar</Link>
          <Link href="/digest" className="inline-flex min-h-11 items-center text-small font-bold">Weekly digest</Link>
          <Link href="/alerts" className="inline-flex min-h-11 items-center text-small font-bold">E-mail alerts (not open yet)</Link>
        </nav>
      </section>

      <FilterNotices notices={notices} />
      {filterForm}

      {(data.funding?.length ?? 0) > 0 && (
        <section aria-labelledby="funding-heading" className="flex flex-col gap-3">
          <h2 id="funding-heading" className="m-0 text-h3">Funding calls: new, and dates moved</h2>
          <p className="m-0 text-small text-ink-muted">
            A call is new on the day we first collected it. A date moved is a closing or opening date the source changed on a call we already held.
            See all <Link href="/funding" className="font-semibold">funding calls</Link>.
          </p>
          <FitFilter />
          <p className="m-0 flex max-w-prose flex-wrap items-center gap-2 text-small text-ink-muted"><Tag kind="programme">New call</Tag>{FIRST_COLLECTED}</p>
          <AutoGrid as="ul" min={420} pairs>
            {data.funding?.map((f) => <FitItem key={f.id} id={f.call.id} className="min-w-0"><FundingChangeEntry change={f} /></FitItem>)}
          </AutoGrid>
        </section>
      )}

      <section aria-labelledby="entries" className="flex flex-col gap-6">
        <h2 id="entries" className="m-0 text-body font-semibold" aria-live="polite">
          {data.total === 0 ? 'No changes in this window' : `Showing ${from}–${to} of ${formatNumber(data.total)} ${plural(data.total, 'change')}`}
        </h2>
        {data.total === 0 ? (
          <EmptyState title="Nothing changed in these filters" action={<Button variant="secondary" href="/changes">Clear filters</Button>}>
            Try another country or a wider choice of what to include. Notices are collected once a day, so a quiet day is possible.
          </EmptyState>
        ) : (
          <>
          {/* WP-106 (p03): only the legend of what is listed ("New" stood over a list of amendments) */}
          {data.items.some((c) => c.kind === 'new') && <p className="m-0 flex max-w-prose flex-wrap items-center gap-2 text-small text-ink-muted"><Tag kind="programme">New</Tag>{FIRST_COLLECTED}</p>}
          {data.items.some((c) => c.kind === 'award') && <p className="m-0 flex max-w-prose flex-wrap items-center gap-2 text-small text-ink-muted"><Tag kind="programme">New award</Tag>{FIRST_COLLECTED_AWARD}</p>}
          {byDay(data.items).map((g) => (
            <div key={g.day} className="flex flex-col gap-3">
              <h2 className="m-0 text-h3"><time dateTime={g.day}>{formatDateUtc(`${g.day}T00:00:00Z`)}</time></h2>
              <AutoGrid as="ul" min={420} pairs>
                {g.items.map((c) => <li key={c.id} className="min-w-0"><ChangeEntry change={c} /></li>)}
              </AutoGrid>
            </div>
          ))}
          </>
        )}
        <Pagination page={data.page} total={data.total} pageSize={data.pageSize} hrefFor={(p) => `/changes${toChangeQuery({ ...filters, page: p })}`} />
      </section>
    </>
  );
}
