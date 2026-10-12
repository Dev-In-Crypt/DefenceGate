import type { Metadata } from 'next';
import { getBuyers } from '@/lib/api';
import { activeBuyerFilterCount, DEFAULT_BUYER_SORT, parseBuyerFilters, toBuyerQuery, type SearchParams } from '@/lib/filters';
import { MIN_LIST_ITEMS, buildMetadata } from '@/lib/seo';
import { BuyerCard } from '@/components/dg/cards';
import { ListPage } from '@/components/dg/list-page';
import { BuyerFilterBar } from '@/components/tenders/filter-bars';

export const revalidate = 3600;

const SORT_OPTIONS = [
  { value: 'tenders', label: 'Most tenders first' },
  { value: 'name', label: 'Name, A to Z' },
];

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseBuyerFilters(await searchParams);
  let noindex = activeBuyerFilterCount(f) > 0 || (f.page ?? 1) > 1 || f.sort !== DEFAULT_BUYER_SORT;
  if (!noindex) {
    try { noindex = (await getBuyers(f)).items.length < MIN_LIST_ITEMS; } catch { noindex = true; }
  }
  return buildMetadata({
    title: 'Defence buyers',
    description: 'Directory of the procurement bodies behind defence and dual-use tenders: how many notices each has published, how many are open now and when it last published.',
    path: '/buyers',
    noindex,
  });
}

export default async function BuyersPage({ searchParams }: Props) {
  const filters = parseBuyerFilters(await searchParams);
  const result = await getBuyers(filters);
  return (
    <ListPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Buyers', href: '/buyers' }]}
      title="Buyers"
      intro="The bodies that publish defence and dual-use tenders. Open a buyer to see everything it has published, open notices first."
      filterBar={<BuyerFilterBar filters={filters} basePath="/buyers" />}
      noun="buyers" page={result.page} pageSize={result.pageSize} total={result.total}
      sort={{ value: filters.sort ?? DEFAULT_BUYER_SORT, options: SORT_OPTIONS }}
      clearHref="/buyers"
      emptyTitle="No buyers match these filters"
      emptyText="Try a shorter name or fewer countries. Only buyers with at least one defence notice in our archive are listed."
      hrefFor={(p) => `/buyers${toBuyerQuery({ ...filters, page: p })}`}
      footnote="Counts come from the notices in our archive. Each notice shows its own source."
    >
      {result.items.map((b) => <li key={b.id}><BuyerCard buyer={b} /></li>)}
    </ListPage>
  );
}
