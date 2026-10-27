import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { getBuyers } from '@/lib/api';
import { formatDateTimeUtc } from '@/lib/format';
import { staleNote } from '@/lib/source-status';
import {
  activeBuyerFilterCount, defaultBuyerSort, ignoredFilters, lastPage, parseBuyerFilters, toBuyerQuery, type SearchParams,
} from '@/lib/filters';
import { MIN_LIST_ITEMS, buildMetadata, listViewTitle } from '@/lib/seo';
import { BuyerCard } from '@/components/dg/cards';
import { ListPage } from '@/components/dg/list-page';
import { BuyerFilterBar } from '@/components/tenders/filter-bars';
import { CoverageNote } from '@/components/dg/coverage-note';

export const revalidate = 60;

const SORT_OPTIONS = [
  { value: 'tenders', label: 'Most tenders first' },
  { value: 'name', label: 'Name, A to Z' },
];
/** WP-98b (p02): with a CPV filter, who bought most under the codes (the default then) */
const CPV_SORT = { value: 'cpv', label: 'Most tenders under these codes first' };

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseBuyerFilters(await searchParams);
  let noindex = activeBuyerFilterCount(f) > 0 || (f.page ?? 1) > 1 || f.sort !== defaultBuyerSort(f.cpv);
  if (!noindex) {
    try { noindex = (await getBuyers(f)).items.length < MIN_LIST_ITEMS; } catch { noindex = true; }
  }
  return buildMetadata({
    title: listViewTitle('Defence buyers', 'Buyers', { page: f.page, countries: f.country, q: f.q, filters: activeBuyerFilterCount(f) }),
    description: 'Directory of the procurement bodies behind defence and dual-use tenders: how many notices each has published, how many are open now and when it last published.',
    path: '/buyers',
    noindex,
  });
}

export default async function BuyersPage({ searchParams }: Props) {
  const sp = await searchParams;
  const filters = parseBuyerFilters(sp);
  const result = await getBuyers(filters);
  // A page past the end is the last page, not an empty list.
  const last = lastPage(result.total, result.pageSize);
  if (result.total > 0 && (filters.page ?? 1) > last) redirect(`/buyers${toBuyerQuery({ ...filters, page: last })}`);
  return (
    <ListPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Buyers', href: '/buyers' }]}
      title="Buyers"
      intro="The bodies that publish defence and dual-use tenders."
      // WP-98b: what we collect for the chosen countries
      scope={<CoverageNote countries={filters.country} />}
      filterBar={<BuyerFilterBar filters={filters} basePath="/buyers" />}
      noun="buyers" page={result.page} pageSize={result.pageSize} total={result.total}
      sort={{ value: filters.sort ?? defaultBuyerSort(filters.cpv), options: filters.cpv?.length ? [CPV_SORT, ...SORT_OPTIONS] : SORT_OPTIONS }}
      clearHref="/buyers"
      notices={[...(result.staleAsOf ? [staleNote(result.staleAsOf, formatDateTimeUtc) as string] : []), ...ignoredFilters(sp, 'buyers')]}
      emptyTitle="No buyers match these filters"
      emptyText="Try a shorter name or fewer countries. Only buyers with at least one defence notice in our archive are listed."
      hrefFor={(p) => `/buyers${toBuyerQuery({ ...filters, page: p })}`}
      footnote={filters.cpv?.length
        ? `Buyers with at least one tender under CPV ${filters.cpv.join(', ')}; the counts are of all their tenders in our archive, except “Under these codes”: those under the codes, ${result.cpvCountCollapsed === false ? 'counted as published (taking too long to tell a notice from its copy in another source, so one published in two may count twice)' : 'each once as the tender list shows it'}. Each notice shows its own source.`
        : 'Counts come from the notices in our archive. Each notice shows its own source.'}
    >
      {result.items.map((b) => <li key={b.id}><BuyerCard buyer={b} /></li>)}
    </ListPage>
  );
}
