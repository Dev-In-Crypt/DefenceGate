import { formatNumber } from '@/lib/format';
import type { Crumb } from '@/lib/seo';
import { EmptyState } from './feedback';
import { PageHeader } from './page-header';
import { Pagination } from './pagination';
import { Button } from './button';
import { ResultTools } from './download-link';
import { FilterNotices } from './filter-notices';
import { SortSelect } from '../funding/filter-panel';
import { LiveListScope, ResultsRegion } from './live-list';

/** The filter column: from lg it stays on screen while the results scroll (and scrolls itself when it is taller than the window). */
export const FILTER_COLUMN = 'flex min-w-0 flex-col gap-4 lg:sticky lg:top-4 lg:-m-1 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:p-1 lg:[scrollbar-width:thin]';

/**
 * A keyboard's way past the filters to the results (WP-58; 59 Tab presses to the first call on /funding before): the first stop of
 * the filter column here, before the chips on the call lists. Hidden until it has focus; the results stay after the filters in the
 * DOM, so the reading order and the layout do not change.
 */
export function SkipToResults() {
  return (
    <a href="#results" className="sr-only focus:not-sr-only focus:inline-flex focus:min-h-11 focus:items-center focus:self-start focus:rounded-pill focus:bg-surface focus:px-5 focus:font-bold">
      Skip to results
    </a>
  );
}

/**
 * Shared shell of the tenders and buyers directories, the same layout as /funding: breadcrumbs, header,
 * filter column, results column (count, sort, items, pagination). `children` are the <li> items.
 */
export function ListPage({
  crumbs, title, intro, head, meta, scope, listNote, filterBar, filterExtra, exportHref, exportStatus, noun, page, pageSize, total, sort, clearHref, emptyTitle, emptyText, hrefFor, footnote, notices = [], totalText, reachable, limitNote, calendarHref = '/calendar?kind=tenders', feedHref, subscribe, children,
}: {
  /** WP-87: the calendar and the Atom feed of this result, with its filters. */
  calendarHref?: string; feedHref?: string;
  /** WP-90: the "Subscribe to this search" control, above the results whatever their number. */
  subscribe?: React.ReactNode;
  crumbs: Crumb[]; title: string; intro?: string; meta?: string; filterBar: React.ReactNode;
  /** Under the title in place of (or after) the intro: the tabs of Companies (WP-86). */
  head?: React.ReactNode;
  /** Said above the results: what the list shows when that is a default the visitor did not choose. */
  scope?: React.ReactNode;
  /** One line that holds for every card of the list (said once instead of on each card), shown above the cards. */
  listNote?: React.ReactNode;
  /** Rendered under the filters (the save-search island). */
  filterExtra?: React.ReactNode;
  /** The CSV of the current result; shown under the filters when there are results. */
  exportHref?: string;
  /** The status filter of that result (it sets the file's row cap). */
  exportStatus?: string;
  noun: string; page: number; pageSize: number; total: number;
  sort: { value: string; options: { value: string; label: string }[] };
  clearHref: string; emptyTitle: string; emptyText: React.ReactNode; hrefFor: (page: number) => string;
  footnote?: React.ReactNode;
  /** Parameters that were not used (see lib/filters.ts ignoredFilters). */
  notices?: string[];
  /** The total as words when it is not an exact count ("10,000 or more", "at least 10,000"). */
  totalText?: string;
  /** How many results the pager can reach when the list stops short of its total (`maxOffset`); the total when absent. */
  reachable?: number;
  /** Said above the pager when the list stops short of its results (lib/list-count.ts cutSentence). */
  limitNote?: string | null;
  children: React.ReactNode;
}) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  // An empty result has one heading, the empty state's: the count line is then a paragraph, not a second h2.
  const Count = total === 0 ? 'p' : 'h2';
  return (
    <>
      <PageHeader crumbs={crumbs} title={title} lead={intro} meta={meta}>{head}</PageHeader>

      <LiveListScope>
      <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)] lg:gap-8">
        <div className={FILTER_COLUMN}>
          <SkipToResults />
          {filterBar}{filterExtra}
          {exportHref && total > 0 && <ResultTools csvHref={exportHref} calendarHref={calendarHref} feedHref={feedHref} className="hidden lg:flex" total={total} status={exportStatus} atLeast={totalText !== undefined} />}
        </div>
        <ResultsRegion id="results" tabIndex={-1} aria-labelledby="results-heading" className="flex min-w-0 flex-col gap-4 outline-none">
          {scope}
          <div className="flex flex-wrap items-center gap-3">
            <Count id="results-heading" className="m-0 mr-auto text-body font-semibold" aria-live="polite">
              {total === 0 ? `No ${noun}` : `Showing ${formatNumber(from)}–${formatNumber(to)} of ${totalText ?? formatNumber(total)} ${noun}`}
            </Count>
            <SortSelect value={sort.value} options={sort.options} />
          </div>
          <FilterNotices notices={notices} />
          {subscribe}
          {total > 0 && listNote}
          {total === 0 ? (
            <EmptyState title={emptyTitle} action={<Button variant="secondary" href={clearHref}>Clear filters</Button>}>{emptyText}</EmptyState>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-4 p-0">{children}</ul>
          )}
          {limitNote && <p className="m-0 max-w-prose text-small text-ink-muted">{limitNote}</p>}
          <Pagination page={page} total={reachable ?? total} pageSize={pageSize} hrefFor={hrefFor} />
          {footnote && (typeof footnote === 'string' ? <p className="m-0 max-w-prose text-small text-ink-muted">{footnote}</p> : footnote)}
          {/* Below lg the filters are folded away and the column is one: the tools come after the results. */}
          {exportHref && total > 0 && <ResultTools csvHref={exportHref} calendarHref={calendarHref} feedHref={feedHref} className="lg:hidden" total={total} status={exportStatus} atLeast={totalText !== undefined} />}
        </ResultsRegion>
      </div>
      </LiveListScope>
    </>
  );
}
