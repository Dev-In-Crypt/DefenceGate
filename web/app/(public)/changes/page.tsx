import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';
import { Rss } from 'lucide-react';
import { getChanges } from '@/lib/api';
import { weekLabel } from '@/lib/digest';
import { lastPage, parseChangeFilters, toChangeQuery, PARAM, type SearchParams } from '@/lib/filters';
import { formatDateTimeUtc, formatDateUtc, formatNumber, plural } from '@/lib/format';
import { staleNote } from '@/lib/source-status';
import { BUYER_COUNTRIES, SCOPE_CHOICES } from '@/lib/taxonomy';
import { buildMetadata } from '@/lib/seo';
import type { Change } from '@/lib/types';
import { AutoGrid } from '@/components/dg/auto-grid';
import { Button } from '@/components/dg/button';
import { EmptyState } from '@/components/dg/feedback';
import { PageHeader } from '@/components/dg/page-header';
import { Select } from '@/components/dg/form';
import { Icon } from '@/components/dg/icon';
import { Pagination } from '@/components/dg/pagination';
import { Tag } from '@/components/dg/tag';
import { ChangeEntry, FIRST_COLLECTED } from '@/components/changes/change-entry';
import { FundingChangeEntry } from '@/components/changes/funding-change-entry';
import { FitFilter, FitItem } from '@/components/funding/fit-badge';

export const revalidate = 60;

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseChangeFilters(await searchParams);
  const meta = buildMetadata({
    title: 'What changed in the last 14 days',
    description: 'New defence and dual-use notices and the amendments to their deadline, value, status or procedure, taken from our archive of observed changes. With an Atom feed.',
    path: '/changes',
    noindex: toChangeQuery({ country: f.country, scope: f.scope, week: f.week, kind: f.kind, page: f.page }) !== '',
  });
  return { ...meta, alternates: { ...meta.alternates, types: { 'application/atom+xml': '/changes.atom' } } };
}

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
  const filters = parseChangeFilters(await searchParams);
  const data = await getChanges(filters).catch(() => null);
  const crumbs = [{ label: 'Home', href: '/' }, { label: 'What changed', href: '/changes' }];
  const header = (
    <PageHeader crumbs={crumbs} title="What changed"
      lead={<>
        {filters.week
          ? `New notices and amendments seen in ${weekLabel(filters.week)}. An amendment is a deadline, value, status or procedure that moved, with the old and the new value.`
          : 'New notices and amendments seen in the last 14 days: a deadline, value, status or procedure that moved, with the old and the new value.'}{' '}
        No account is needed, and the Atom feed does what an alert would.
      </>} />
  );
  const country = filters.country?.[0] ?? '';
  const filterForm = (
    <form method="get" action="/changes" role="search" aria-label="Filter changes" className="flex flex-col gap-4 rounded-lg border border-transparent bg-surface p-5 sm:flex-row sm:flex-wrap sm:items-end">
      <Select name={PARAM.country} label="Buyer country" placeholder="All countries" defaultValue={country} className="sm:min-w-56"
        options={Object.entries(BUYER_COUNTRIES).map(([code, name]) => ({ value: code, label: `${name} (${code})` }))} />
      <Select name={PARAM.scope} label="What to include" placeholder={SCOPE_CHOICES.relevant.label} defaultValue={filters.scope ?? ''}
        className="sm:min-w-72" options={SCOPE_OPTIONS} />
      {filters.week && <input type="hidden" name="week" value={filters.week} />}
      {filters.kind && <input type="hidden" name="kind" value={filters.kind} />}
      <div className="flex items-center gap-3">
        <Button type="submit">Apply</Button>
        <Link href="/changes" className="inline-flex min-h-11 items-center text-small font-bold">Clear</Link>
      </div>
    </form>
  );
  // A week outside the archive, or not yet ended, is a 404 of the API: not a fault of the list.
  if (!data && filters.week) notFound();
  if (!data) {
    // The filters stay (a visitor who picked a country should not start over), and the way out is a retry.
    return (
      <>
        {header}
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
  const feedHref = `/changes.atom${toChangeQuery({ country: filters.country, scope: filters.scope })}`;
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
          <h2 id="window" className="m-0 text-h3">{filters.week ? weekLabel(filters.week) : <>The last {data.windowDays} days</>}</h2>
          <p className="m-0 max-w-prose text-body">
            <span className="font-mono tabular-nums">{formatNumber(data.counts.new)}</span> new notices and{' '}
            <span className="font-mono tabular-nums">{formatNumber(data.counts.amended)}</span> amendments, from{' '}
            <time dateTime={data.windowFrom}>{formatDateUtc(data.windowFrom)}</time> to{' '}
            <time dateTime={windowLast}>{formatDateUtc(windowLast)}</time> (UTC).
          </p>
          {(filters.week || filters.kind) && (
            <p className="m-0 max-w-prose text-body">
              {filters.kind ? `Only the ${filters.kind === 'new' ? 'new notices' : 'amendments'} are listed. ` : ''}
              {filters.week && <>This is the list behind <Link href={`/digest/${filters.week}`} className="font-semibold">the weekly digest of this week</Link>. </>}
              <Link href="/changes" className="font-semibold">{filters.week ? 'Show the last 14 days' : 'Show all changes'}</Link>
            </p>
          )}
          {(data.fundingTotal ?? 0) > 0 && (
            <p className="m-0 max-w-prose text-body">
              <span className="font-mono tabular-nums">{formatNumber(data.fundingTotal ?? 0)}</span> funding calls are new or had a date moved by the source; they are listed{' '}
              <a href="#funding-heading" className="font-semibold">below</a>, apart from the notices.
            </p>
          )}
          <p className="m-0 max-w-prose text-small text-ink-muted">
            Taken from our own archive, which began in September 2026: an amendment is a change we observed in a source, on the day we saw it, which may be
            later than the day the buyer made it. Our own corrections and re-readings are never listed, nor are changes we only learned of by loading a
            source&rsquo;s older notices (a notice&rsquo;s own page lists those as earlier changes). A notice counts as new only if it was published in these
            days. A notice published in several places is listed once. One entry is one notice on one day.
          </p>
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
          <p className="m-0 flex max-w-prose flex-wrap items-center gap-2 text-small text-ink-muted"><Tag kind="programme">New</Tag>{FIRST_COLLECTED}</p>
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
