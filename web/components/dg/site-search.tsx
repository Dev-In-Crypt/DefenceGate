import { ArrowRight, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './button';
import { Icon } from './icon';
import { CONTROL, boxCls } from './field';

/**
 * The site search (WP-86): a GET to /search, which asks tenders, funding, buyers and companies at once. `compact` is the
 * header's field (the label read out, not shown; a 44 px search button); otherwise the label is shown with a "Search" button
 * (home, /search). Works without script.
 */
export function SiteSearchForm({ id, compact = false, defaultValue, className }: {
  id: string; compact?: boolean; defaultValue?: string; className?: string;
}) {
  const label = 'Search tenders, funding, buyers and companies';
  return (
    <form method="get" action="/search" role="search" aria-label="Site search" className={cn('flex min-w-0 items-end gap-2', !compact && 'flex-wrap', className)}>
      {/* The full form: the button goes under the field when both do not fit (a phone). */}
      <div className={cn('flex min-w-0 flex-1 flex-col gap-1', !compact && 'basis-64')}>
        <label htmlFor={id} className={compact ? 'sr-only' : 'text-label text-ink'}>{label}</label>
        <div className={cn(boxCls(undefined, false, true), compact && 'px-3')}>
          {!compact && <Icon icon={Search} className="shrink-0 text-ink-muted" />}
          <input id={id} type="search" name="q" required minLength={2} maxLength={100} defaultValue={defaultValue} autoComplete="off"
            placeholder={compact ? 'Search' : 'For example Rheinmetall, radar or drone'} className={CONTROL} />
        </div>
      </div>
      {compact ? (
        <button type="submit" aria-label="Search" className="flex size-11 shrink-0 items-center justify-center rounded-pill bg-surface-inset text-ink">
          <Icon icon={Search} />
        </button>
      ) : <Button type="submit" iconRight={ArrowRight} className="shrink-0">Search</Button>}
    </form>
  );
}
