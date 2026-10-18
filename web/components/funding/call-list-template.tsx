import Link from 'next/link';
import { CalendarDays, List } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDateTimeUtc, repeatedCallBudgets } from '@/lib/format';
import { PARAM, describeCallFilters, toQuery } from '@/lib/filters';
import { listUpdatedAt } from '@/lib/source-status';
import { fundersWithCoverage } from '@/lib/taxonomy';
import type { CallFilters, Health, ListView, Paginated, Call } from '@/lib/types';
import type { Crumb } from '@/lib/seo';
import { Breadcrumbs, EmptyState } from '../dg/feedback';
import { CallCard } from '../dg/cards';
import { Pagination } from '../dg/pagination';
import { Button } from '../dg/button';
import { ResultTools } from '../dg/download-link';
import { FilterNotices } from '../dg/filter-notices';
import { Icon } from '../dg/icon';
import { FilterBar, type FilterGroup } from './filter-bar';
import { SortSelect } from './filter-panel';
import { CallCalendar } from './call-calendar';

const SORT_OPTIONS = [
  { value: 'deadline-asc', label: 'Deadline, soonest first' },
  { value: 'deadline-desc', label: 'Deadline, latest first' },
  { value: 'budget-desc', label: 'Budget, largest first' },
];

export interface EntryChip { label: string; href: string }

/** A way of loosening one filter of an empty list, with how many calls it would show. */
export interface Alternative { label: string; total: number; filters: CallFilters }

/** Shared template for /funding and every /funding/* list sub-page. */
export function CallListTemplate({
  title, intro, basePath, crumbs, filters, result, view, health, chips = [], hide, saveSearch, exportHref, notices = [], alternatives = [],
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
}) {
  // An empty result has one heading, the empty state's: the count line is then a paragraph, not a second h2.
  const Count = result.total === 0 ? 'p' : 'h2';
  // The time of the data (`meta.updatedAt`), never the render time; left out when the API does not send it.
  const updated = listUpdatedAt(result);
  const repeats = repeatedCallBudgets(result.items);
  const from = result.total === 0 ? 0 : (result.page - 1) * result.pageSize + 1;
  const to = Math.min(result.total, result.page * result.pageSize);
  const viewHref = (v: ListView) => `${basePath}${toQuery({ ...filters, page: 1 }, { [PARAM.view]: v === 'calendar' ? v : undefined })}`;

  return (
    <>
      <Breadcrumbs items={crumbs} />
      <header className="flex flex-col gap-3">
        <h1 className="m-0 text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1">{title}</h1>
        <p className="m-0 max-w-[62ch] text-body text-ink-muted">{intro}</p>
        <p className="m-0 font-mono text-mono text-ink-muted">{health.sources.filter((s) => s.type === 'grants').length} funding sources{updated ? ` · Data updated ${formatDateTimeUtc(updated)}` : ''}</p>
      </header>

      {chips.length > 0 && (
        <nav aria-label="Browse funding" className="-mx-4 overflow-x-auto px-4">
          <ul className="m-0 flex w-max list-none gap-2 p-0 md:w-auto md:flex-wrap">
            {chips.map((c) => (
              <li key={c.href}>
                <Link href={c.href} className="inline-flex min-h-11 items-center rounded-pill bg-surface px-4 text-small font-bold text-ink no-underline transition-colors duration-dg hover:bg-surface-inset hover:no-underline">{c.label}</Link>
              </li>
            ))}
          </ul>
        </nav>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <FilterBar filters={filters} basePath={basePath} hide={hide} view={view === 'calendar' ? view : undefined}
            countries={fundersWithCoverage(health.sources, filters.country)} cascadeTotal={result.cascadeTotal} ukraineTotal={result.ukraineTotal} />
          {saveSearch}
          {exportHref && result.total > 0 && <ResultTools csvHref={exportHref} calendarHref="/calendar?kind=funding" className="hidden lg:flex" total={result.total} status={filters.status} />}
        </div>

        <section aria-labelledby="results-heading" className="flex min-w-0 flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Count id="results-heading" className="m-0 mr-auto text-body font-semibold" aria-live="polite">
              {result.total === 0 ? 'No calls' : view === 'calendar' ? `${result.total} calls` : `Showing ${from}–${to} of ${result.total} calls`}
            </Count>
            {view === 'list' && <SortSelect value={filters.sort ?? 'deadline-asc'} options={SORT_OPTIONS} />}
            <div role="group" aria-label="View" className="flex rounded-pill bg-surface p-1">
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
          {result.search && result.search.alsoSearched.length > 0 && (
            <p className="m-0 text-small text-ink-muted">Also searched: {result.search.alsoSearched.join(', ')}.</p>
          )}
          {result.total === 0 ? (
            <EmptyState title="No calls match" action={<Button variant="secondary" href={basePath}>Clear filters</Button>}>
              <p className="m-0">Nothing matches {describeCallFilters(filters).join(', ')}.</p>
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
            <ul className="m-0 flex list-none flex-col gap-4 p-0">
              {result.items.map((c) => <li key={c.id}><CallCard call={c} budgetRepeated={repeats.has(c.id)} /></li>)}
            </ul>
          )}

          {view === 'list' && (
            <Pagination page={result.page} total={result.total} pageSize={result.pageSize}
              hrefFor={(p) => `${basePath}${toQuery({ ...filters, page: p })}`} />
          )}
          {/* Below lg the filters are folded away and the column is one: the tools come after the results. */}
          {exportHref && result.total > 0 && <ResultTools csvHref={exportHref} calendarHref="/calendar?kind=funding" className="lg:hidden" total={result.total} status={filters.status} />}
        </section>
      </div>
    </>
  );
}
