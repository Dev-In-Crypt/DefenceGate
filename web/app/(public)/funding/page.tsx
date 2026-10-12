import type { Metadata } from 'next';
import { getCalls, getHealth } from '@/lib/api';
import { activeFilterCount, parseCallFilters, parseView, type SearchParams } from '@/lib/filters';
import { buildMetadata } from '@/lib/seo';
import { CallListTemplate, type EntryChip } from '@/components/funding/call-list-template';

export const revalidate = 3600;
const CALENDAR_LIMIT = 500;

const CHIPS: EntryChip[] = [
  { label: 'Open now', href: '/funding/open' },
  { label: 'Closing soon', href: '/funding/closing-soon' },
  { label: 'EDF', href: '/funding/programme/edf' },
  { label: 'EDIP', href: '/funding/programme/edip' },
  { label: 'Horizon Europe', href: '/funding/programme/horizon' },
  { label: 'Digital Europe', href: '/funding/programme/digital' },
  { label: 'National', href: '/funding/programme/national' },
  { label: 'Defence', href: '/funding/regime/defence' },
  { label: 'Dual-use', href: '/funding/regime/dual-use' },
  { label: 'PL Poland', href: '/funding/country/pl' },
  { label: 'SE Sweden', href: '/funding/country/se' },
  { label: 'FR France', href: '/funding/country/fr' },
  { label: 'ES Spain', href: '/funding/country/es' },
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
      intro="EU and national funding for defence and dual-use projects, in English. Every deadline is in UTC and every call links to its source."
      basePath="/funding"
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Funding', href: '/funding' }]}
      filters={filters} result={result} view={view} health={health} chips={CHIPS}
    />
  );
}
