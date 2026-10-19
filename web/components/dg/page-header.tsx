import { cn } from '@/lib/utils';
import type { Crumb } from '@/lib/seo';
import { Breadcrumbs } from './feedback';

/**
 * The head of every page: breadcrumbs, h1, lead, optional mono meta line, optional actions. One unit with its own
 * rhythm (12 px between the parts), so the breadcrumb sits with the title and not a whole section away from it; the
 * page (`main`) puts 32 px (48 from md) between this block and what follows.
 *
 *   <PageHeader crumbs={[...]} title="Weekly digest" lead="..." meta="12 sources" actions={<Button/>} />
 *
 * `lead` is the opening paragraph: 18/28 in the ink colour, at most one reading measure wide. `children` render under
 * the lead (a row of tags, a status). `crumbs` is optional: the signed-in pages have none.
 */
export function PageHeader({ crumbs, title, sub, lead, meta, actions, children, titleProps, className }: {
  crumbs?: Crumb[];
  title: React.ReactNode;
  /** A line right under the title (a week, a date range), 20/28. */
  sub?: React.ReactNode;
  lead?: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  /** Extra props of the h1 (`lang`, a tone class). */
  titleProps?: { lang?: string; className?: string };
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col gap-3', className)}>
      {crumbs && <Breadcrumbs items={crumbs} />}
      <header className="flex flex-col gap-3">
        <h1 lang={titleProps?.lang} className={cn('page-title m-0 break-words', titleProps?.className)}>{title}</h1>
        {sub && <p className="m-0 max-w-prose text-h3">{sub}</p>}
        {lead && <p className="lead m-0 max-w-prose">{lead}</p>}
        {meta && <p className="m-0 font-mono text-mono text-ink-muted">{meta}</p>}
        {children}
        {actions && <div className="flex flex-wrap items-center gap-3 pt-1">{actions}</div>}
      </header>
    </div>
  );
}
