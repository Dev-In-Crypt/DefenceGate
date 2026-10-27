import { ArrowRight, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './button';
import { Icon } from './icon';
import { CONTROL, boxCls } from './field';

/** WP-121: short enough for the field at 320 px ("For example Rheinmetall, radar or drone" was cut to "...radar or dro"). */
const PLACEHOLDER = 'Rheinmetall, radar, drone';

/**
 * The site search (WP-86): a GET to /search, which asks tenders, funding, buyers and companies at once. `compact` is the
 * header's field (the label read out, not shown; a 44 px search button). Otherwise it is the page search (home, /search), WP-149:
 * the label 8 px above a 56 px field that takes the whole width of its column, the Search button beside it at the same height
 * (under it, full width, on a phone). Works without script.
 */
export function SiteSearchForm({ id, compact = false, defaultValue, className }: {
  id: string; compact?: boolean; defaultValue?: string; className?: string;
}) {
  const label = 'Search tenders, funding, buyers and companies';
  const input = (
    <input id={id} type="search" name="q" required minLength={2} maxLength={100} defaultValue={defaultValue} autoComplete="off"
      placeholder={compact ? 'Search' : PLACEHOLDER} className={CONTROL} />
  );
  if (compact) {
    return (
      // WP-130: the header's search has a name of its own: on /search two landmarks were both "Site search"
      <form method="get" action="/search" role="search" aria-label="Header search" className={cn('flex min-w-0 items-end gap-2', className)}>
        <div className="flex min-w-0 flex-1 flex-col">
          <label htmlFor={id} className="sr-only">{label}</label>
          <div className={cn(boxCls(undefined, false, true), 'px-3')}>{input}</div>
        </div>
        <button type="submit" aria-label="Search" className="flex size-11 shrink-0 items-center justify-center rounded-pill bg-surface-inset text-ink">
          <Icon icon={Search} />
        </button>
      </form>
    );
  }
  return (
    <form method="get" action="/search" role="search" aria-label="Site search" className={cn('flex w-full min-w-0 flex-col gap-2', className)}>
      <label htmlFor={id} className="text-small font-semibold text-ink">{label}</label>
      <div className="flex min-w-0 flex-wrap gap-2 sm:flex-nowrap">
        <div className={cn(boxCls(undefined, false, true), 'h-14 min-w-0 flex-1 basis-full px-5 sm:basis-auto')}>
          <Icon icon={Search} className="shrink-0 text-ink-muted" />
          {input}
        </div>
        <Button type="submit" iconRight={ArrowRight} className="min-h-14 w-full shrink-0 px-7 text-body sm:w-auto">Search</Button>
      </div>
    </form>
  );
}
