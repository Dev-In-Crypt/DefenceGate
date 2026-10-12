import type { Metadata } from 'next';
import { getCalls, getHealth } from '@/lib/api';
import { filtersFromQuery } from '@/lib/account-format';
import { activeFilterCount, parseCallFilters, parseView, toQuery, type SearchParams } from '@/lib/filters';
import { buildMetadata } from '@/lib/seo';
import { CallListTemplate, type EntryChip } from '@/components/funding/call-list-template';
import { SaveSearch } from '@/components/account/save-search';

export const revalidate = 3600;
const CALENDAR_LIMIT = 500;

// Entry chips are filter links on this page (the filter values are the API's codes); there are no per-filter hub pages.
const CHIPS: EntryChip[] = [
  { label: 'Open now', href: '/funding?status=open' },
  { label: 'Closing soon', href: '/funding?status=closing-soon' },
  { label: 'EDF', href: '/funding?programme=EDF' },
  { label: 'EDIP', href: '/funding?programme=EDIP' },
  { label: 'Horizon Europe', href: '/funding?programme=HORIZON' },
  { label: 'Digital Europe', href: '/funding?programme=DIGITAL' },
  { label: 'National', href: '/funding?programme=NATIONAL' },
  { label: 'Defence', href: '/funding?regime=defence' },
  { label: 'Dual-use', href: '/funding?regime=dual-use' },
  { label: 'PL Poland', href: '/funding?country=PL' },
  { label: 'SE Sweden', href: '/funding?country=SE' },
  { label: 'FR France', href: '/funding?country=FR' },
  { label: 'ES Spain', href: '/funding?country=ES' },
];

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseCallFilters(await searchParams);
  // Filtered views are shareable but canonicalise to /funding and stay out of the index.
  return buildMetadata({
    title: 'Defence and dual-use funding calls',
    description: 'Open EU and national funding calls for defence and dual-use projects: EDF, EDIP, Horizon Europe, Digital Europe and national programmes. Deadlines in UTC, sourced daily.',
    path: '/funding',
    noindex: activeFilterCount(f) > 0 || (f.page ?? 1) > 1,
  });
}

export default async function FundingHubPage({ searchParams }: Props) {
  const sp = await searchParams;
  const filters = parseCallFilters(sp);
  const view = parseView(sp);
  const [result, health] = await Promise.all([
    getCalls(view === 'calendar' ? { ...filters, page: 1, pageSize: CALENDAR_LIMIT } : filters),
    getHealth(),
  ]);
  return (
    <CallListTemplate
      title="Funding calls"
      intro="EU and national funding for defence and dual-use projects. Every deadline is in UTC and every call links to its source."
      basePath="/funding"
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Funding', href: '/funding' }]}
      filters={filters} result={result} view={view} health={health} chips={CHIPS}
      saveSearch={<SaveSearch kind="call" filters={filtersFromQuery(toQuery({ ...filters, page: 1 }))} />}
      exportHref={`/funding/export.csv${toQuery({ ...filters, page: 1 })}`}
    />
  );
}
