import type { Metadata } from 'next';
import { getHealth, getTenders } from '@/lib/api';
import { activeTenderFilterCount, DEFAULT_TENDER_SORT, parseTenderFilters, toTenderQuery, type SearchParams } from '@/lib/filters';
import { formatDateTimeUtc } from '@/lib/format';
import { MIN_LIST_ITEMS, buildMetadata } from '@/lib/seo';
import { TenderCard } from '@/components/dg/cards';
import { ListPage } from '@/components/dg/list-page';
import { TenderFilterBar } from '@/components/tenders/filter-bars';

export const revalidate = 3600;

const SORT_OPTIONS = [
  { value: 'deadline-asc', label: 'Deadline, soonest first' },
  { value: 'published-desc', label: 'Published, newest first' },
];

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseTenderFilters(await searchParams);
  // Filtered, sorted or paged views are shareable but canonicalise to /tenders and stay out of the index.
  let noindex = activeTenderFilterCount(f) > 0 || (f.page ?? 1) > 1 || f.sort !== DEFAULT_TENDER_SORT || f.currency !== 'EUR';
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
  const filters = parseTenderFilters(await searchParams);
  const [result, health] = await Promise.all([getTenders(filters), getHealth()]);
  const tenderSources = health.sources.filter((s) => s.type === 'tenders').length;
  return (
    <ListPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Tenders', href: '/tenders' }]}
      title="Tenders"
      intro="Procurement notices from defence buyers, in one list. Every deadline is in UTC, every notice links to its source, and every change we observe is kept in its version history."
      meta={`${tenderSources} tender sources · Last update ${formatDateTimeUtc(health.generatedAt)}`}
      filterBar={<TenderFilterBar filters={filters} basePath="/tenders" />}
      noun="tenders" page={result.page} pageSize={result.pageSize} total={result.total}
      sort={{ value: filters.sort ?? DEFAULT_TENDER_SORT, options: SORT_OPTIONS }}
      clearHref="/tenders"
      emptyTitle="No tenders match these filters"
      emptyText="Try a wider deadline range or fewer countries. Closed tenders are hidden unless you choose Closed or All, and notices that only supply a defence buyer are hidden unless you choose Supplies to defence buyers or All."
      hrefFor={(p) => `/tenders${toTenderQuery({ ...filters, page: p })}`}
      footnote="Amounts are shown in the currency the source states and are never converted or added up across currencies."
    >
      {result.items.map((t) => <li key={t.id}><TenderCard tender={t} /></li>)}
    </ListPage>
  );
}
