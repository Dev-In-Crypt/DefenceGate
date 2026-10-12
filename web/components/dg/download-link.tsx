import Link from 'next/link';
import { CalendarDays, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import { buttonVariants } from './button';
import { Icon } from './icon';

/**
 * The tools of a result list, under the filters: the CSV of the current result (a plain link, not a
 * client-routed one, so nothing prefetches the file) and a way to the deadline calendar.
 */
export function ResultTools({ csvHref, calendarHref = '/calendar', className }: { csvHref: string; calendarHref?: string; className?: string }) {
  return (
    <div className={cn('flex flex-col gap-2 rounded-lg bg-surface p-5', className)}>
      <a href={csvHref} download className={cn(buttonVariants({ variant: 'secondary', fullWidth: true }))}>
        <Icon icon={Download} size="button" />Download CSV
      </a>
      <p className="m-0 text-small text-ink-muted">The public fields of this result, up to 2,000 rows (1,000 when the status is All), with source, licence and attribution on every row.</p>
      <Link href={calendarHref} className="inline-flex min-h-11 items-center gap-2 text-small font-bold">
        <Icon icon={CalendarDays} size="inline" />Deadline calendar
      </Link>
    </div>
  );
}
