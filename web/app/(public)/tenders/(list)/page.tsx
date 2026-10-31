import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { getHealth, getTenderScopeCounts, getTenders } from '@/lib/api';
import { filtersFromQuery } from '@/lib/account-format';
import {
  activeTenderFilterCount, defaultTenderSort, ignoredFilters, lastPage, parseTenderFilters, tenderSortOptions, toTenderQuery, type SearchParams,
} from '@/lib/filters';
import { formatDateTimeUtc } from '@/lib/format';
import { SCOPE_COUNTS_GRACE_MS, cutSentence, listStamps, reachableTotal, totalWords, within } from '@/lib/list-count';
import { calendarHrefFor } from '@/lib/calendar';
import { NOTICE_NUMBER } from '@/lib/search-terms';
import { SubscribeToSearch } from '@/components/tenders/subscribe';
import { listUpdatedAt, staleNote, updatedLine, valueMissingNote, valueMissingNotes } from '@/lib/source-status';
import { tooBroad } from '@/lib/export-cache';
import { MIN_LIST_ITEMS, buildMetadata, listViewTitle } from '@/lib/seo';
import { TenderCard } from '@/components/dg/cards';
import { ClassifiedNote } from '@/components/dg/basis-chips';
import { ListPage } from '@/components/dg/list-page';
import { TenderFilterBar } from '@/components/tenders/filter-bars';
import { AlsoSearched, CpvHints, GroupSuggestions } from '@/components/tenders/search-terms-note';
import { SaveSearch } from '@/components/account/save-search';
import { FilterChips } from '@/components/tenders/filter-chips';
import { CoverageNote } from '@/components/dg/coverage-note';

export const revalidate = 60;

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseTenderFilters(await searchParams);
  // Filtered, sorted or paged views are shareable but canonicalise to /tenders and stay out of the index.
  let noindex = activeTenderFilterCount(f) > 0 || (f.page ?? 1) > 1 || f.sort !== defaultTenderSort(f.status);
  if (!noindex) {
    // The default list is also what the page renders (same cached fetch); a thin one is not indexed.
    try { noindex = (await getTenders(f)).items.length < MIN_LIST_ITEMS; } catch { noindex = true; }
  }
  return buildMetadata({
    title: listViewTitle('Defence and dual-use tenders', 'Tenders', { page: f.page, countries: f.country, q: f.q, filters: activeTenderFilterCount(f) }),
    description: 'Open procurement notices from defence buyers across Europe, from TED and national portals. Deadlines in UTC, every notice linked to its source and its version history.',
    path: '/tenders',
    noindex,
  });
}

export default async function TendersPage({ searchParams }: Props) {
  const sp = await searchParams;
  const filters = parseTenderFilters(sp);
  // WP-101: a notice number is looked for in every status unless a status was chosen (Open hid an awarded notice: 220199-2026)
  if (filters.q && NOTICE_NUMBER.test(filters.q) && sp.status === undefined) redirect(`/tenders${toTenderQuery({ ...filters, status: 'all', sort: undefined, page: 1 })}`);
  // WP-127: the counts beside the scope choices never hold the page up for longer than the list itself takes, plus a moment
  const counts = getTenderScopeCounts(filters);
  const [result, health] = await Promise.all([getTenders(filters), getHealth()]);
  const scopeCounts = await within(counts, SCOPE_COUNTS_GRACE_MS);
  const missing = valueMissingNotes(health.sources);
  const stale = staleNote(result.staleAsOf, formatDateTimeUtc);
  // A page past the end is the last page, not an empty list.
  // The list serves no position past `maxOffset`, so the last page is the last one it can show (and never a 503).
  const reachable = reachableTotal(result);
  // WP-110: a hint opens the same list by the code instead of the words
  const cpvHref = (prefix: string) => `/tenders${toTenderQuery({ ...filters, q: undefined, cpv: [prefix], page: 1 })}`;
  const last = lastPage(reachable, result.pageSize);
  if (reachable > 0 && (filters.page ?? 1) > last) redirect(`/tenders${toTenderQuery({ ...filters, page: last })}`);
  const tenderSources = health.sources.filter((s) => s.type === 'tenders').length;
  // The time of the data (`meta.updatedAt`), never the render time; the line is left out when the API does not send it.
  const updated = listUpdatedAt(result);
  // WP-87: one stamp for the list and its scope counts when they are of the same minute; two, each named, when not
  const stamps = listStamps(result, scopeCounts);
  return (
    <ListPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Tenders', href: '/tenders' }]}
      title="Tenders"
      intro="Procurement notices from defence buyers in one list, each linked to its source with its changes kept."
      meta={`${tenderSources} tender sources · Deadlines in UTC${updated ? ` · ${updatedLine(updated, result.meta?.updatedBy)}` : ''}${stamps.list ? ` · ${stamps.list}` : ''}`}
      // WP-98b: the filters as chips (phone) and what we collect for the chosen countries, above the results (an empty one too)
      scope={<><FilterChips filters={filters} basePath="/tenders" /><CoverageNote countries={filters.country} /></>}
      filterBar={<TenderFilterBar filters={filters} basePath="/tenders" scopeCounts={scopeCounts} countsNote={stamps.scope} />}
      calendarHref={calendarHrefFor(filters)}
      // WP-90: the change feed (and the calendar file) of this search are in one control above the results, with every filter
      subscribe={<SubscribeToSearch filters={filters} />}
      // The accounts service keeps open, closed and all; a saved search for Planned would be refused.
      filterExtra={filters.status === 'planned' ? undefined : <SaveSearch kind="tender" filters={filtersFromQuery(toTenderQuery({ ...filters, page: 1, pageSize: undefined }))} />}
      // Every status and scope with nothing to narrow them is refused by the export (400): no link to a refusal.
      exportHref={tooBroad(filters) ? undefined : `/tenders/export.csv${toTenderQuery({ ...filters, page: 1, pageSize: undefined })}`}
      exportStatus={filters.status}
      noun="tenders" page={result.page} pageSize={result.pageSize} total={result.total}
      totalText={totalWords(result)} reachable={reachable} limitNote={cutSentence(result)}
      sort={{ value: filters.sort ?? defaultTenderSort(filters.status), options: tenderSortOptions(filters.status) }}
      notices={[...(stale ? [stale] : []), ...ignoredFilters(sp, 'tenders')]}
      clearHref="/tenders"
      listNote={<><AlsoSearched also={result.alsoSearched} /><CpvHints hints={result.cpvHints} hrefFor={cpvHref} /><ClassifiedNote tenders={result.items} /></>}
      emptyTitle="No tenders match these filters"
      emptyText={<>
        Try a wider deadline range or fewer countries. Closed tenders are hidden unless you choose Closed or All, and a military product code bought by a municipality or a hospital (dual-use) is hidden unless you choose the scope All.
        {/* WP-98: the words name a product group: its codes find notices whatever language their titles are in */}
        <AlsoSearched also={result.alsoSearched} />
        <CpvHints hints={result.cpvHints} hrefFor={cpvHref} />
        <GroupSuggestions groups={result.searchGroups} hrefFor={(cpv) => `/tenders${toTenderQuery({ ...filters, q: undefined, cpv, page: 1 })}`} />
      </>}
      hrefFor={(p) => `/tenders${toTenderQuery({ ...filters, page: p })}`}
      // WP-160: after the results (a link above them would be the page's first /tenders/ link, which e2e specs read as a notice)
      footnote={<>
        <p className="m-0 max-w-prose text-small text-ink-muted">Amounts are shown in the currency the source states and are never converted or added up across currencies.</p>
        <p className="m-0 max-w-prose text-small text-ink-muted">Where the next tenders come from: <Link href="/tenders/ending" className="font-bold" data-ending-link>contracts ending soon</Link>, by the contract periods the notices state.</p>
      </>}
    >
      {result.items.map((t) => <li key={t.id}><TenderCard tender={t} cpvFilter={filters.cpv} classifiedNote={false} valueNote={valueMissingNote(missing, t.source.sourceId)} /></li>)}
    </ListPage>
  );
}
