import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { getHealth, getTenderScopeCounts, getTenders } from '@/lib/api';
import { filtersFromQuery } from '@/lib/account-format';
import {
  activeTenderFilterCount, defaultTenderSort, ignoredFilters, lastPage, parseTenderFilters, toTenderQuery, type SearchParams,
} from '@/lib/filters';
import { formatDateTimeUtc } from '@/lib/format';
import { listUpdatedAt, staleNote, valueMissingNote, valueMissingShares } from '@/lib/source-status';
import { tooBroad } from '@/lib/export-cache';
import { MIN_LIST_ITEMS, buildMetadata } from '@/lib/seo';
import { TenderCard } from '@/components/dg/cards';
import { ClassifiedNote } from '@/components/dg/basis-chips';
import { ListPage } from '@/components/dg/list-page';
import { TenderFilterBar } from '@/components/tenders/filter-bars';
import { SaveSearch } from '@/components/account/save-search';

export const revalidate = 60;

const SORT_OPTIONS = [
  { value: 'deadline-asc', label: 'Deadline, soonest first' },
  { value: 'deadline-desc', label: 'Deadline, latest first' },
  { value: 'published-desc', label: 'Published, newest first' },
];

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseTenderFilters(await searchParams);
  // Filtered, sorted or paged views are shareable but canonicalise to /tenders and stay out of the index.
  let noindex = activeTenderFilterCount(f) > 0 || (f.page ?? 1) > 1 || f.sort !== defaultTenderSort(f.status) || f.currency !== 'EUR';
  if (!noindex) {
    // The default list is also what the page renders (same cached fetch); a thin one is not indexed.
    try { noindex = (await getTenders(f)).items.length < MIN_LIST_ITEMS; } catch { noindex = true; }
  }
  return buildMetadata({
    title: 'Defence and dual-use tenders',
    description: 'Open procurement notices from defence buyers across Europe, from TED and national portals. Deadlines in UTC, every notice linked to its source and its version history.',
    path: '/tenders',
    noindex,
  });
}

export default async function TendersPage({ searchParams }: Props) {
  const sp = await searchParams;
  const filters = parseTenderFilters(sp);
  const [result, health, scopeCounts] = await Promise.all([getTenders(filters), getHealth(), getTenderScopeCounts(filters)]);
  const missing = valueMissingShares(health.sources);
  const stale = staleNote(result.staleAsOf, formatDateTimeUtc);
  // A page past the end is the last page, not an empty list.
  const last = lastPage(result.total, result.pageSize);
  if (result.total > 0 && (filters.page ?? 1) > last) redirect(`/tenders${toTenderQuery({ ...filters, page: last })}`);
  const tenderSources = health.sources.filter((s) => s.type === 'tenders').length;
  // The time of the data (`meta.updatedAt`), never the render time; the line is left out when the API does not send it.
  const updated = listUpdatedAt(result);
  return (
    <ListPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Tenders', href: '/tenders' }]}
      title="Tenders"
      intro="Procurement notices from defence buyers, in one list. Every deadline is in UTC, every notice links to its source, and changes to dates, values and status are kept in its version history."
      meta={`${tenderSources} tender sources${updated ? ` · Data updated ${formatDateTimeUtc(updated)}` : ''}`}
      filterBar={<TenderFilterBar filters={filters} basePath="/tenders" scopeCounts={scopeCounts} />}
      filterExtra={<SaveSearch kind="tender" filters={filtersFromQuery(toTenderQuery({ ...filters, page: 1 }))} />}
      // Every status and scope with nothing to narrow them is refused by the export (400): no link to a refusal.
      exportHref={tooBroad(filters) ? undefined : `/tenders/export.csv${toTenderQuery({ ...filters, page: 1 })}`}
      exportStatus={filters.status}
      noun="tenders" page={result.page} pageSize={result.pageSize} total={result.total}
      sort={{ value: filters.sort ?? defaultTenderSort(filters.status), options: SORT_OPTIONS }}
      notices={[...(stale ? [stale] : []), ...ignoredFilters(sp, 'tenders')]}
      clearHref="/tenders"
      listNote={<ClassifiedNote tenders={result.items} />}
      emptyTitle="No tenders match these filters"
      emptyText="Try a wider deadline range or fewer countries. Closed tenders are hidden unless you choose Closed or All, and a military product code bought by a municipality or a hospital (dual-use) is hidden unless you choose the scope All."
      hrefFor={(p) => `/tenders${toTenderQuery({ ...filters, page: p })}`}
      footnote="Amounts are shown in the currency the source states and are never converted or added up across currencies."
    >
      {result.items.map((t) => <li key={t.id}><TenderCard tender={t} cpvFilter={filters.cpv} classifiedNote={false} valueNote={valueMissingNote(missing, t.source.sourceId)} /></li>)}
    </ListPage>
  );
}
