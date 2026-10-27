import Link from 'next/link';
import { CalendarDays, List } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDateTimeUtc, plural, repeatedCallBudgets } from '@/lib/format';
import { DEFAULT_CURRENCY, PARAM, defaultCallSort, describeCallFilters, dualUseStart, toQuery } from '@/lib/filters';
import { listUpdatedAt, updatedLine } from '@/lib/source-status';
import { fundersWithCoverage } from '@/lib/taxonomy';
import type { CallFilters, Health, ListView, Paginated, Call } from '@/lib/types';
import type { Crumb } from '@/lib/seo';
import { EmptyState } from '../dg/feedback';
import { PageHeader } from '../dg/page-header';
import { CallCard } from '../dg/cards';
import { Pagination } from '../dg/pagination';
import { Button } from '../dg/button';
import { ResultTools } from '../dg/download-link';
import { FILTER_COLUMN, SkipToResults } from '../dg/list-page';
import { FilterNotices } from '../dg/filter-notices';
import { Icon } from '../dg/icon';
import { FilterBar, type FilterGroup } from './filter-bar';
import { FitCount, FitFilter, FitList, type WholeList } from './fit-badge';
import { SortSelect } from './filter-panel';
import { LiveListScope, ResultsRegion } from '../dg/live-list';
import { CallCalendar } from './call-calendar';
import { emptyLine } from '@/lib/funding-path';
import { notCollected } from '@/lib/text-search';

const sortOptions = (currency: string) => [
  { value: 'deadline-asc', label: 'Deadline, soonest first' },
  { value: 'deadline-desc', label: 'Deadline, latest first' },
  { value: 'budget-desc', label: `Budget, largest first (${currency} first)` },
];

export interface EntryChip { label: string; href: string }

/** A way of loosening one filter of an empty list, with how many calls it would show. */
export interface Alternative { label: string; total: number; filters: CallFilters }

/** WP-91: of an empty Open list, the same filters' calls that open next and that closed last (the first few of each, and the totals). */
export interface Fallback { upcoming: Call[]; upcomingTotal: number; closed: Call[]; closedTotal: number }

/** Shared template for /funding and every /funding/* list sub-page. */
export function CallListTemplate({
  title, intro, basePath, crumbs, filters, result, view, health, chips = [], hide, saveSearch, exportHref, notices = [], alternatives = [], fallback, icsHref,
  fitAll = false, subscribe,
}: {
  title: string; intro: string; basePath: string; crumbs: Crumb[]; filters: CallFilters;
  result: Paginated<Call>; view: ListView; health: Health; chips?: EntryChip[]; hide?: FilterGroup[];
  /** Rendered under the filters (the save-search island). */
  saveSearch?: React.ReactNode;
  /** The CSV of the current result; shown under the filters when there are results. */
  exportHref?: string;
  /** Parameters that were not used (see lib/filters.ts ignoredFilters). */
  notices?: string[];
  /** Of an empty list: the looser searches that find something (see lib/filters.ts broadenings). */
  alternatives?: Alternative[];
  /** Of an empty Open list: what opens next and what closed last, for the same filters (WP-91). */
  fallback?: Fallback;
  /** The calendar file of this search (WP-91: /funding.ics with the list's filters). */
  icsHref?: string;
  /** WP-99: "Fits my profile" is on: every call of the search is on this page (`fit=1`), so the filter and the topics see all of them. */
  fitAll?: boolean;
  /** WP-99: the "Subscribe to this search" block (calendar and Atom feed of these filters). */
  subscribe?: React.ReactNode;
}) {
  // An empty result has one heading, the empty state's: the count line is then a paragraph, not a second h2.
  const Count = result.total === 0 ? 'p' : 'h2';
  // The time of the data (`meta.updatedAt`), never the render time; left out when the API does not send it.
  const updated = listUpdatedAt(result);
  const repeats = repeatedCallBudgets(result.items);
  // WP-87: in the default order the defence calls come first; the dual-use ones (the API orders them last) get a heading of their own
  const dualAt = dualUseStart(result.items, (filters.sort ?? defaultCallSort(filters.status)) === defaultCallSort(filters.status));
  const from = result.total === 0 ? 0 : (result.page - 1) * result.pageSize + 1;
  const to = Math.min(result.total, result.page * result.pageSize);
  const viewHref = (v: ListView) => `${basePath}${toQuery({ ...filters, page: 1 }, { [PARAM.view]: v === 'calendar' ? v : undefined })}`;
  const whole: WholeList = { on: fitAll, total: result.total, onHref: `${basePath}${toQuery({ ...filters, page: 1 }, { fit: '1' })}#results`, offHref: `${basePath}${toQuery({ ...filters, page: 1 })}` };
  // WP-99 (p09): the deadline calendar of this search keeps the search
  const calendarHref = viewHref('calendar');

  return (
    <>
      <PageHeader crumbs={crumbs} title={title} lead={intro}
        meta={`${health.sources.filter((s) => s.type === 'grants').length} funding sources · Deadlines in UTC${updated ? ` · ${updatedLine(updated, null)}` : ''}`} />

      {/* Before the chips and the filters: from the top of the page to the first call in a few stops (WP-58). */}
      <SkipToResults />

      {chips.length > 0 && (
        <nav aria-label="Browse funding" className="-mx-4 overflow-x-auto px-4 sm:-mx-6 sm:px-6 md:mx-0 md:overflow-visible md:px-0">
          <ul className="m-0 flex w-max list-none gap-2 p-0 md:w-auto md:flex-wrap">
            {chips.map((c) => (
              <li key={c.href}>
                <Link href={c.href} className="inline-flex min-h-11 items-center rounded-pill border border-transparent bg-surface px-4 text-small font-bold text-ink no-underline transition-colors duration-dg hover:bg-surface-inset hover:no-underline">{c.label}</Link>
              </li>
            ))}
          </ul>
        </nav>
      )}

      <LiveListScope>
      <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)] lg:gap-8">
        <div className={FILTER_COLUMN}>
          <FilterBar filters={filters} basePath={basePath} hide={hide} view={view === 'calendar' ? view : undefined}
            countries={fundersWithCoverage(health.sources, filters.country)} cascadeTotal={result.cascadeTotal} ukraineTotal={result.ukraineTotal} uaNoFundingTotal={result.uaNoFundingTotal} />
          {saveSearch}
          {exportHref && result.total > 0 && <ResultTools csvHref={exportHref} calendarHref={calendarHref} icsHref={filters.status === 'closed' ? undefined : icsHref} className="hidden lg:flex" total={result.total} status={filters.status} />}
          {result.total > 0 && filters.status !== 'closed' && subscribe && <div className="hidden lg:block">{subscribe}</div>}
        </div>

        <ResultsRegion id="results" tabIndex={-1} aria-labelledby="results-heading" className="flex min-w-0 flex-col gap-4 outline-none">
          <div className="flex flex-wrap items-center gap-3">
            <Count id="results-heading" className="m-0 mr-auto text-body font-semibold" aria-live="polite">
              {result.total === 0 ? 'No calls' : view === 'calendar' ? `${result.total} ${plural(result.total, 'call')}` : (
                <FitCount text={fitAll ? `${result.total} ${plural(result.total, 'call')}` : `Showing ${from}–${to} of ${result.total} ${plural(result.total, 'call')}`}
                  ids={result.items.map((c) => c.id)} total={result.total} whole={fitAll} />
              )}
            </Count>
            {view === 'list' && <SortSelect value={filters.sort ?? 'deadline-asc'} options={sortOptions(filters.currency ?? DEFAULT_CURRENCY)} />}
            <div role="group" aria-label="View" className="flex rounded-pill border border-transparent bg-surface p-1">
              {(['list', 'calendar'] as const).map((v) => (
                <Link key={v} href={viewHref(v)} aria-current={view === v ? 'true' : undefined}
                  className={cn('inline-flex min-h-9 items-center gap-1.5 rounded-pill px-3 text-small font-bold no-underline hover:no-underline',
                    view === v ? 'bg-primary text-on-primary' : 'text-ink hover:bg-surface-inset')}>
                  <Icon icon={v === 'list' ? List : CalendarDays} size="inline" />{v === 'list' ? 'List' : 'Calendar'}
                </Link>
              ))}
            </div>
          </div>

          <FilterNotices notices={notices} />
          {/* Below lg the filters are folded away and the column is one. WP-106 (p09): the tools before the results, not after 38,000 px of them. */}
          {exportHref && result.total > 0 && <ResultTools csvHref={exportHref} calendarHref={calendarHref} icsHref={filters.status === 'closed' ? undefined : icsHref} className="lg:hidden" compact total={result.total} status={filters.status} />}
          {view === 'list' && result.total > 0 && <FitFilter whole={whole} />}
          {result.search && result.search.alsoSearched.length > 0 && (
            <p className="m-0 text-small text-ink-muted">Also searched: {result.search.alsoSearched.join(', ')}.</p>
          )}
          {result.total === 0 && fallback && (fallback.upcoming.length > 0 || fallback.closed.length > 0) ? (
            <div className="flex flex-col gap-4" data-empty-fallback>
              <h2 className="m-0 text-h3">{emptyLine(filters, fallback.upcoming, fallback.closed)}</h2>
              {notCollected(filters.q).map((s) => <p key={s} className="m-0 text-body" data-not-collected>{s}</p>)}
              {fallback.upcoming.length > 0 && (
                <section aria-labelledby="fallback-upcoming" className="flex flex-col gap-3">
                  <h3 id="fallback-upcoming" className="m-0 text-h4">Opening next</h3>
                  <ul className="m-0 flex list-none flex-col gap-4 p-0">{fallback.upcoming.map((c) => <li key={c.id}><CallCard call={c} headingLevel="h3" /></li>)}</ul>
                  {fallback.upcomingTotal > fallback.upcoming.length && <Link href={`${basePath}${toQuery({ ...filters, status: 'forthcoming', sort: undefined, page: 1 })}`} className="font-semibold">All {fallback.upcomingTotal} calls of this search that open soon</Link>}
                </section>
              )}
              {fallback.closed.length > 0 && (
                <section aria-labelledby="fallback-closed" className="flex flex-col gap-3">
                  <h3 id="fallback-closed" className="m-0 text-h4">Closed recently</h3>
                  <ul className="m-0 flex list-none flex-col gap-4 p-0">{fallback.closed.map((c) => <li key={c.id}><CallCard call={c} headingLevel="h3" /></li>)}</ul>
                  {fallback.closedTotal > fallback.closed.length && <Link href={`${basePath}${toQuery({ ...filters, status: 'closed', sort: undefined, page: 1 })}`} className="font-semibold">All {fallback.closedTotal} closed calls of this search</Link>}
                </section>
              )}
            </div>
          ) : result.total === 0 ? (
            <EmptyState title="No calls match" action={<Button variant="secondary" href={basePath}>Clear filters</Button>}>
              <p className="m-0">Nothing matches {describeCallFilters(filters).join(', ')}.</p>
              {notCollected(filters.q).map((s) => <p key={s} className="m-0" data-not-collected>{s}</p>)}
              {alternatives.length > 0 && (
                <ul className="m-0 mt-3 flex list-none flex-col gap-1 p-0">
                  {alternatives.map((a) => (
                    <li key={a.label}>
                      <Link href={`${basePath}${toQuery(a.filters)}`} className="font-semibold">
                        {a.total} {a.total === 1 ? 'call matches' : 'calls match'} {a.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </EmptyState>
          ) : view === 'calendar' ? (
            <CallCalendar calls={result.items} />
          ) : (
            <FitList className="m-0 flex list-none flex-col gap-4 p-0" items={result.items.map((c, i) => ({
              id: c.id, text: [c.title, c.originalTitle, ...c.scope].filter(Boolean).join(' '),
              node: <CallCard call={c} budgetRepeated={repeats.has(c.id)} />,
              heading: i === dualAt ? <DualUseHeading others={`${basePath}${toQuery({ ...filters, regime: ['defence'], page: 1 })}`} /> : undefined,
            }))} />
          )}

          {view === 'list' && !fitAll && (
            <Pagination page={result.page} total={result.total} pageSize={result.pageSize}
              hrefFor={(p) => `${basePath}${toQuery({ ...filters, page: p })}`} />
          )}
          {result.total > 0 && filters.status !== 'closed' && subscribe && <div className="lg:hidden">{subscribe}</div>}
        </ResultsRegion>
      </div>
      </LiveListScope>
    </>
  );
}

/** The heading of the dual-use part of the list (WP-87), before its first call (left out while "Fits my profile" re-orders the list). */
function DualUseHeading({ others }: { others: string }) {
  return (
    <li className="flex flex-col gap-1 pt-2" data-dual-use-heading>
      <h3 className="m-0 text-h3">Dual-use calls</h3>
      <p className="m-0 max-w-prose text-small text-ink-muted">
        Calls for research and products with civil and defence uses, listed after the defence calls. <Link href={others} className="font-semibold">Show only defence calls</Link>.
      </p>
    </li>
  );
}
