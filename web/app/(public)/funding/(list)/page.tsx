import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { getCalls, getHealth } from '@/lib/api';
import { filtersFromQuery } from '@/lib/account-format';
import { activeFilterCount, broadenings, ignoredFilters, lastPage, parseCallFilters, parseView, toQuery, type SearchParams } from '@/lib/filters';
import { buildMetadata, listViewTitle } from '@/lib/seo';
import { CallListTemplate, type EntryChip } from '@/components/funding/call-list-template';
import { SaveSearch } from '@/components/account/save-search';

export const revalidate = 60;
const CALENDAR_LIMIT = 500;
const MAX_ALTERNATIVES = 4;

// Entry chips are filter links on this page (the filter values are the API's codes); there are no per-filter hub pages.
const CHIPS: EntryChip[] = [
  { label: 'Open now', href: '/funding?status=open' },
  { label: 'Closing soon', href: '/funding?status=closing-soon' },
  // EDIP calls (identifiers EDF-EDIP-...) are filed under EDF by the portal, so there is one chip for both.
  { label: 'EDF and EDIP', href: '/funding?programme=EDF' },
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
    title: listViewTitle('Defence and dual-use funding calls', 'Funding calls', { page: f.page, countries: f.country, q: f.q, filters: activeFilterCount(f) }),
    description: 'Open EU and national funding calls for defence and dual-use projects: EDF (including its EDIP calls), Horizon Europe, Digital Europe and national programmes. Deadlines in UTC, collected daily.',
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
  // A page past the end is the last page, not an empty list.
  const last = lastPage(result.total, result.pageSize);
  if (view === 'list' && result.total > 0 && (filters.page ?? 1) > last) redirect(`/funding${toQuery({ ...filters, page: last })}`);
  // An empty list says which filter to loosen: each looser search is counted (one call each, at most four).
  const alternatives = result.total === 0 && view === 'list'
    ? (await Promise.all(broadenings(filters).slice(0, MAX_ALTERNATIVES).map(async (b) => ({
      label: b.label, filters: b.filters,
      total: (await getCalls({ ...b.filters, pageSize: 1 }).catch(() => null))?.total ?? 0,
    })))).filter((a) => a.total > 0)
    : [];
  return (
    <CallListTemplate
      title="Funding calls"
      intro="EU and national funding for defence and dual-use projects. Every deadline is in UTC, and a call links to its source page where the source gives one."
      basePath="/funding"
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Funding', href: '/funding' }]}
      filters={filters} result={result} view={view} health={health} chips={CHIPS} alternatives={alternatives}
      notices={ignoredFilters(sp, 'funding')}
      saveSearch={<SaveSearch kind="call" filters={filtersFromQuery(toQuery({ ...filters, page: 1 }))} />}
      exportHref={`/funding/export.csv${toQuery({ ...filters, page: 1 })}`}
    />
  );
}
