import type { Metadata } from 'next';
import { notFound, redirect } from 'next/navigation';
import { ApiError } from '@/lib/api';
import { getOrganisations } from '@/lib/networks-api';
import { formatDateTimeUtc } from '@/lib/format';
import { staleNote } from '@/lib/source-status';
import { activeOrgFilterCount, defaultOrgSort, parseOrgFilters, toOrgQuery } from '@/lib/networks';
import { lastPage, type SearchParams } from '@/lib/filters';
import { MIN_LIST_ITEMS, buildMetadata, listViewTitle } from '@/lib/seo';
import { ErrorState } from '@/components/dg/feedback';
import { ListPage } from '@/components/dg/list-page';
import { CountryNote, DataSources, OrgCard, OrgFilterBar, ProgrammeScope } from '@/components/networks/parts';

export const revalidate = 60;

const SORT_OPTIONS = [
  { value: 'defence', label: 'Most defence projects first' },
  { value: 'projects', label: 'Most projects first, all programmes' },
  { value: 'name', label: 'Name, A to Z' },
];

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseOrgFilters(await searchParams);
  let noindex = activeOrgFilterCount(f) > 0 || (f.page ?? 1) > 1 || f.sort !== defaultOrgSort(f);
  if (!noindex) {
    try { noindex = (await getOrganisations(f)).items.length < MIN_LIST_ITEMS; } catch { noindex = true; }
  }
  return buildMetadata({
    title: listViewTitle('Organisations in EU-funded defence and research projects', 'Organisations', { page: f.page, countries: f.country, q: f.q, filters: activeOrgFilterCount(f) }),
    description: 'Who has taken part in the European Defence Fund, Horizon Europe, Horizon 2020 and FP7 projects: each organisation with its projects, partners, countries and EU funding, from CORDIS and the EDF project factsheets.',
    path: '/organisations',
    noindex,
  });
}

export default async function OrganisationsPage({ searchParams }: Props) {
  const filters = parseOrgFilters(await searchParams);
  let result;
  try {
    result = await getOrganisations(filters);
  } catch (e) {
    // The API serves no position beyond its cap (10,000): a page past it is not there, which is an answer, not a fault.
    if (e instanceof ApiError && e.status === 422) notFound();
    return <ErrorState title="We could not load the organisations" retryHref="/organisations" />;
  }
  const last = lastPage(result.total, result.pageSize);
  if (result.total > 0 && (filters.page ?? 1) > last) redirect(`/organisations${toOrgQuery({ ...filters, page: last })}`);
  return (
    <>
      <ListPage
        crumbs={[{ label: 'Home', href: '/' }, { label: 'Organisations', href: '/organisations' }]}
        title="Organisations in funded projects"
        intro="Who has already taken part in EU-funded defence and research projects: the European Defence Fund, Horizon Europe, Horizon 2020 and FP7. Open an organisation to see its projects, its partners and the EU funding it received."
        scope={<ProgrammeScope filters={filters} basePath="/organisations" />}
        filterBar={<OrgFilterBar filters={filters} basePath="/organisations" />}
        noun="organisations" page={result.page} pageSize={result.pageSize} total={result.total}
        totalText={result.totalExact ? undefined : `${result.total.toLocaleString('en-GB')} or more`}
        sort={{ value: filters.sort ?? defaultOrgSort(filters), options: SORT_OPTIONS }}
        notices={result.staleAsOf ? [staleNote(result.staleAsOf, formatDateTimeUtc) as string] : []}
        clearHref="/organisations"
        emptyTitle="No organisations match these filters"
        emptyText="Try a shorter name or fewer filters. Only organisations that took part in at least one project we hold are listed."
        hrefFor={(p) => `/organisations${toOrgQuery({ ...filters, page: p })}`}
        footnote="Counts are projects with an active participant, as the sources list them today. Defence projects are those of the European Defence Fund and its predecessors (EDIDP, PADR); the other figures count every programme, civil research included. A name that looks like a natural person is not listed; to ask for a removal, write to the contact in the imprint (privacy notice, section 9)."
      >
        {result.items.map((o) => <li key={o.id}><OrgCard org={o} scope={defaultOrgSort(filters) === 'defence' ? 'defence' : 'all'} /></li>)}
      </ListPage>
      <CountryNote />
      <DataSources sources={result.meta.sources} amountNote={result.meta.amountNote} />
    </>
  );
}
