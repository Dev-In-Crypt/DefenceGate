import type { Crumb } from '@/lib/seo';
import { EmptyState } from './feedback';
import { PageHeader } from './page-header';
import { Pagination } from './pagination';
import { Button } from './button';
import { ResultTools } from './download-link';
import { FilterNotices } from './filter-notices';
import { SortSelect } from '../funding/filter-panel';

/** The filter column: from lg it stays on screen while the results scroll (and scrolls itself when it is taller than the window). */
export const FILTER_COLUMN = 'flex min-w-0 flex-col gap-4 lg:sticky lg:top-4 lg:-m-1 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:p-1 lg:[scrollbar-width:thin]';

/**
 * Shared shell of the tenders and buyers directories, the same layout as /funding: breadcrumbs, header,
 * filter column, results column (count, sort, items, pagination). `children` are the <li> items.
 */
export function ListPage({
  crumbs, title, intro, meta, scope, listNote, filterBar, filterExtra, exportHref, exportStatus, noun, page, pageSize, total, sort, clearHref, emptyTitle, emptyText, hrefFor, footnote, notices = [], totalText, children,
}: {
  crumbs: Crumb[]; title: string; intro: string; meta?: string; filterBar: React.ReactNode;
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
  clearHref: string; emptyTitle: string; emptyText: string; hrefFor: (page: number) => string;
  footnote?: string;
  /** Parameters that were not used (see lib/filters.ts ignoredFilters). */
  notices?: string[];
  /** The total as words when it is not an exact count ("10,000 or more"). */
  totalText?: string;
  children: React.ReactNode;
}) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  // An empty result has one heading, the empty state's: the count line is then a paragraph, not a second h2.
  const Count = total === 0 ? 'p' : 'h2';
  return (
    <>
      <PageHeader crumbs={crumbs} title={title} lead={intro} meta={meta} />

      <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)] lg:gap-8">
        <div className={FILTER_COLUMN}>
          {filterBar}{filterExtra}
          {exportHref && total > 0 && <ResultTools csvHref={exportHref} calendarHref="/calendar?kind=tenders" className="hidden lg:flex" total={total} status={exportStatus} />}
        </div>
        <section aria-labelledby="results-heading" className="flex min-w-0 flex-col gap-4">
          {scope}
          <div className="flex flex-wrap items-center gap-3">
            <Count id="results-heading" className="m-0 mr-auto text-body font-semibold" aria-live="polite">
              {total === 0 ? `No ${noun}` : `Showing ${from}–${to} of ${totalText ?? total} ${noun}`}
            </Count>
            <SortSelect value={sort.value} options={sort.options} />
          </div>
          <FilterNotices notices={notices} />
          {total > 0 && listNote}
          {total === 0 ? (
            <EmptyState title={emptyTitle} action={<Button variant="secondary" href={clearHref}>Clear filters</Button>}>{emptyText}</EmptyState>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-4 p-0">{children}</ul>
          )}
          <Pagination page={page} total={total} pageSize={pageSize} hrefFor={hrefFor} />
          {footnote && <p className="m-0 max-w-prose text-small text-ink-muted">{footnote}</p>}
          {/* Below lg the filters are folded away and the column is one: the tools come after the results. */}
          {exportHref && total > 0 && <ResultTools csvHref={exportHref} calendarHref="/calendar?kind=tenders" className="lg:hidden" total={total} status={exportStatus} />}
        </section>
      </div>
    </>
  );
}
