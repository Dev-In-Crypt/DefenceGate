import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { Rss } from 'lucide-react';
import { getChanges } from '@/lib/api';
import { lastPage, parseChangeFilters, toChangeQuery, PARAM, type SearchParams } from '@/lib/filters';
import { formatDateTimeUtc, formatDateUtc, formatNumber } from '@/lib/format';
import { staleNote } from '@/lib/source-status';
import { BUYER_COUNTRIES, SCOPE_CHOICES } from '@/lib/taxonomy';
import { buildMetadata } from '@/lib/seo';
import type { Change } from '@/lib/types';
import { Button } from '@/components/dg/button';
import { EmptyState } from '@/components/dg/feedback';
import { PageHeader } from '@/components/dg/page-header';
import { Select } from '@/components/dg/form';
import { Icon } from '@/components/dg/icon';
import { Pagination } from '@/components/dg/pagination';
import { ChangeEntry } from '@/components/changes/change-entry';
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
    noindex: toChangeQuery({ country: f.country, scope: f.scope, page: f.page }) !== '',
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
        New notices and amendments seen in the last 14 days: a deadline, value, status or procedure that moved, with the old and the new value.
        No account is needed, and the Atom feed does what an alert would.
      </>} />
  );
  const country = filters.country?.[0] ?? '';
  const filterForm = (
    <form method="get" action="/changes" role="search" aria-label="Filter changes" className="flex flex-col gap-4 rounded-lg border border-edge bg-surface p-5 sm:flex-row sm:items-end">
      <Select name={PARAM.country} label="Buyer country" placeholder="All countries" defaultValue={country} className="sm:min-w-56"
        options={Object.entries(BUYER_COUNTRIES).map(([code, name]) => ({ value: code, label: `${name} (${code})` }))} />
      <Select name={PARAM.scope} label="What to include" placeholder={SCOPE_CHOICES.relevant.label} defaultValue={filters.scope ?? ''}
        className="sm:min-w-72" options={SCOPE_OPTIONS} />
      <div className="flex items-center gap-3">
        <Button type="submit">Apply</Button>
        <Link href="/changes" className="inline-flex min-h-11 items-center text-small font-bold">Clear</Link>
      </div>
    </form>
  );
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
  const from = data.total === 0 ? 0 : (data.page - 1) * data.pageSize + 1;
  const to = Math.min(data.total, data.page * data.pageSize);
  return (
    <>
      {header}
      {data.staleAsOf && (
        <p role="status" className="m-0 rounded-md bg-surface-inset px-4 py-3 text-small text-ink">{staleNote(data.staleAsOf, formatDateTimeUtc)}</p>
      )}

      <section aria-labelledby="window" className="flex flex-col gap-3 rounded-lg border border-edge bg-surface p-5 sm:p-6">
        <h2 id="window" className="m-0 text-h3">The last {data.windowDays} days</h2>
        <p className="m-0 text-body">
          <span className="font-mono tabular-nums">{formatNumber(data.counts.new)}</span> new notices and{' '}
          <span className="font-mono tabular-nums">{formatNumber(data.counts.amended)}</span> amendments, from{' '}
          <time dateTime={data.windowFrom}>{formatDateUtc(data.windowFrom)}</time> to <time dateTime={data.windowTo}>{formatDateUtc(data.windowTo)}</time> (UTC).
        </p>
        {(data.fundingTotal ?? 0) > 0 && (
          <p className="m-0 text-body">
            <span className="font-mono tabular-nums">{formatNumber(data.fundingTotal ?? 0)}</span> funding calls are new or had a date moved by the source; they are listed{' '}
            <a href="#funding-heading" className="font-semibold">below</a>, apart from the notices.
          </p>
        )}
        <p className="m-0 text-small text-ink-muted">
          Taken from our own archive, which began in September 2026: an amendment is a change we observed in a source, on the day we saw it, which may be
          later than the day the buyer made it. Our own corrections and re-readings are never listed, nor are changes we only learned of by loading a
          source&rsquo;s older notices (a notice&rsquo;s own page lists those as earlier changes). A notice counts as new only if it was published in these
          days. A notice published in several places is listed once. One entry is one notice on one day.
        </p>
        <div className="flex flex-wrap gap-x-6">
          <a href={feedHref} className="inline-flex min-h-11 items-center gap-2 text-small font-bold">
            <Icon icon={Rss} size="inline" />Atom feed of this list
          </a>
          <Link href="/calendar" className="inline-flex min-h-11 items-center text-small font-bold">Deadline calendar</Link>
          <Link href="/digest" className="inline-flex min-h-11 items-center text-small font-bold">Weekly digest</Link>
          <Link href="/alerts" className="inline-flex min-h-11 items-center text-small font-bold">E-mail alerts (not open yet)</Link>
        </div>
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
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {data.funding?.map((f) => <FitItem key={f.id} id={f.call.id}><FundingChangeEntry change={f} /></FitItem>)}
          </ul>
        </section>
      )}

      <section aria-labelledby="entries" className="flex flex-col gap-6">
        <h2 id="entries" className="m-0 text-body font-semibold" aria-live="polite">
          {data.total === 0 ? 'No changes in this window' : `Showing ${from}–${to} of ${formatNumber(data.total)} changes`}
        </h2>
        {data.total === 0 ? (
          <EmptyState title="Nothing changed in these filters" action={<Button variant="secondary" href="/changes">Clear filters</Button>}>
            Try another country or a wider choice of what to include. Notices are collected once a day, so a quiet day is possible.
          </EmptyState>
        ) : (
          byDay(data.items).map((g) => (
            <div key={g.day} className="flex flex-col gap-3">
              <h2 className="m-0 text-h3"><time dateTime={g.day}>{formatDateUtc(`${g.day}T00:00:00Z`)}</time></h2>
              <ul className="m-0 flex list-none flex-col gap-3 p-0">
                {g.items.map((c) => <li key={c.id}><ChangeEntry change={c} /></li>)}
              </ul>
            </div>
          ))
        )}
        <Pagination page={data.page} total={data.total} pageSize={data.pageSize} hrefFor={(p) => `/changes${toChangeQuery({ ...filters, page: p })}`} />
      </section>
    </>
  );
}
