import type { Crumb } from '@/lib/seo';
import { Breadcrumbs, EmptyState } from './feedback';
import { Pagination } from './pagination';
import { Button } from './button';
import { ResultTools } from './download-link';
import { SortSelect } from '../funding/filter-panel';

/**
 * Shared shell of the tenders and buyers directories, the same layout as /funding: breadcrumbs, header,
 * filter column, results column (count, sort, items, pagination). `children` are the <li> items.
 */
export function ListPage({
  crumbs, title, intro, meta, filterBar, filterExtra, exportHref, noun, page, pageSize, total, sort, clearHref, emptyTitle, emptyText, hrefFor, footnote, children,
}: {
  crumbs: Crumb[]; title: string; intro: string; meta?: string; filterBar: React.ReactNode;
  /** Rendered under the filters (the save-search island). */
  filterExtra?: React.ReactNode;
  /** The CSV of the current result; shown under the filters when there are results. */
  exportHref?: string;
  noun: string; page: number; pageSize: number; total: number;
  sort: { value: string; options: { value: string; label: string }[] };
  clearHref: string; emptyTitle: string; emptyText: string; hrefFor: (page: number) => string;
  footnote?: string; children: React.ReactNode;
}) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <>
      <Breadcrumbs items={crumbs} />
      <header className="flex flex-col gap-3">
        <h1 className="m-0 text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1">{title}</h1>
        <p className="m-0 max-w-[62ch] text-body text-ink-muted">{intro}</p>
        {meta && <p className="m-0 font-mono text-mono text-ink-muted">{meta}</p>}
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        {filterExtra || (exportHref && total > 0) ? (
          <div className="flex min-w-0 flex-col gap-4">
            {filterBar}{filterExtra}
            {exportHref && total > 0 && <ResultTools csvHref={exportHref} calendarHref="/calendar?kind=tenders" className="hidden lg:flex" />}
          </div>
        ) : filterBar}
        <section aria-labelledby="results-heading" className="flex min-w-0 flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <h2 id="results-heading" className="m-0 mr-auto text-body font-semibold" aria-live="polite">
              {total === 0 ? `No ${noun}` : `Showing ${from}–${to} of ${total} ${noun}`}
            </h2>
            <SortSelect value={sort.value} options={sort.options} />
          </div>
          {total === 0 ? (
            <EmptyState title={emptyTitle} action={<Button variant="secondary" href={clearHref}>Clear filters</Button>}>{emptyText}</EmptyState>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-4 p-0">{children}</ul>
          )}
          <Pagination page={page} total={total} pageSize={pageSize} hrefFor={hrefFor} />
          {footnote && <p className="m-0 text-small text-ink-muted">{footnote}</p>}
          {/* Below lg the filters are folded away and the column is one: the tools come after the results. */}
          {exportHref && total > 0 && <ResultTools csvHref={exportHref} calendarHref="/calendar?kind=tenders" className="lg:hidden" />}
        </section>
      </div>
    </>
  );
}
