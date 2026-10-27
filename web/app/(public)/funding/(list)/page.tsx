import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { getCalls, getHealth } from '@/lib/api';
import { filtersFromQuery } from '@/lib/account-format';
import { activeFilterCount, broadenings, ignoredFilters, lastPage, parseCallFilters, parseView, toQuery, type SearchParams } from '@/lib/filters';
import { buildMetadata, listViewTitle } from '@/lib/seo';
import { CallListTemplate, type EntryChip } from '@/components/funding/call-list-template';
import { SaveSearch } from '@/components/account/save-search';
import { SubscribeToFunding } from '@/components/funding/subscribe';

export const revalidate = 60;
const CALENDAR_LIMIT = 500;
const MAX_ALTERNATIVES = 4;
const FALLBACK_ITEMS = 3;
/** WP-99: "Fits my profile" on (`fit=1`): every call of the search on one page, at most the API's page ceiling, so the filter sees them all. */
const FIT_ALL = 500;

// Entry chips are filter links on this page (the filter values are the API's codes); there are no per-filter hub pages.
const CHIPS: EntryChip[] = [
  { label: 'Open now', href: '/funding?status=open' },
  { label: 'Closing soon', href: '/funding?status=closing-soon' },
  // EDIP calls (identifiers EDF-EDIP-...) are filed under EDF by the portal, so there is one chip for both; the Ukraine Support Instrument has its own (WP-91).
  { label: 'EDF and EDIP', href: '/funding?programme=EDF' },
  { label: 'EDIP USI (Ukraine)', href: '/funding?programme=EDIP-USI' },
  { label: 'Open to companies', href: '/funding?who=companies' },
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
  const sp = await searchParams;
  const f = parseCallFilters(sp);
  // Filtered views are shareable but canonicalise to /funding and stay out of the index.
  return buildMetadata({
    title: listViewTitle('Defence and dual-use funding calls', 'Funding calls', { page: f.page, countries: f.country, q: f.q, filters: activeFilterCount(f) }),
    description: 'Open EU and national funding calls for defence and dual-use projects: EDF (including its EDIP calls), Horizon Europe, Digital Europe and national programmes. Deadlines in UTC, collected daily.',
    path: '/funding',
    noindex: activeFilterCount(f) > 0 || (f.page ?? 1) > 1 || sp.fit === '1',
  });
}

export default async function FundingHubPage({ searchParams }: Props) {
  const sp = await searchParams;
  const filters = parseCallFilters(sp);
  const view = parseView(sp);
  const fitAll = view === 'list' && sp.fit === '1';
  const [result, health] = await Promise.all([
    getCalls(view === 'calendar' ? { ...filters, page: 1, pageSize: CALENDAR_LIMIT } : fitAll ? { ...filters, page: 1, pageSize: FIT_ALL } : filters),
    getHealth(),
  ]);
  // A page past the end is the last page, not an empty list.
  const last = lastPage(result.total, result.pageSize);
  if (view === 'list' && !fitAll && result.total > 0 && (filters.page ?? 1) > last) redirect(`/funding${toQuery({ ...filters, page: last })}`);
  // An empty list says which filter to loosen: each looser search is counted (one call each, at most four).
  const alternatives = result.total === 0 && view === 'list'
    ? (await Promise.all(broadenings(filters).slice(0, MAX_ALTERNATIVES).map(async (b) => ({
      label: b.label, filters: b.filters,
      total: (await getCalls({ ...b.filters, pageSize: 1 }).catch(() => null))?.total ?? 0,
    })))).filter((a) => a.total > 0)
    : [];
  // WP-91 (UX audit 6: /funding?country=PL was a dead end): an empty Open or Closing-soon list shows, for the same filters, the calls
  // that open next and the ones that closed last, with a sentence that says so. Every entry chip lands on calls or on this.
  const empty = result.total === 0 && view === 'list' && (filters.status === 'open' || filters.status === 'closing-soon');
  const [upcoming, closed] = empty
    ? await Promise.all([
      getCalls({ ...filters, status: 'forthcoming', sort: undefined, page: 1, pageSize: FALLBACK_ITEMS }).catch(() => null),
      getCalls({ ...filters, status: 'closed', sort: undefined, page: 1, pageSize: FALLBACK_ITEMS }).catch(() => null),
    ])
    : [null, null];
  return (
    <CallListTemplate
      title="Funding"
      intro="EU and national funding calls for defence and dual-use projects, each linked to its source."
      basePath="/funding"
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Funding', href: '/funding' }]}
      filters={filters} result={result} view={view} health={health} chips={CHIPS} alternatives={alternatives}
      fallback={empty ? { upcoming: upcoming?.items ?? [], upcomingTotal: upcoming?.total ?? 0, closed: closed?.items ?? [], closedTotal: closed?.total ?? 0 } : undefined}
      icsHref={`/funding.ics${toQuery({ ...filters, page: 1 })}`}
      notices={ignoredFilters(sp, 'funding')}
      saveSearch={<SaveSearch kind="call" filters={filtersFromQuery(toQuery({ ...filters, page: 1 }))} />}
      exportHref={`/funding/export.csv${toQuery({ ...filters, page: 1 })}`}
      fitAll={fitAll}
      subscribe={<SubscribeToFunding filters={filters} />}
    />
  );
}
