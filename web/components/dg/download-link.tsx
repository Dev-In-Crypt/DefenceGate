import Link from 'next/link';
import { CalendarDays, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import { exportCap, EXPORT_ROW_CAP } from '@/lib/export-cache';
import { buttonVariants } from './button';
import { Icon } from './icon';

/**
 * The tools of a result list, under the filters: the CSV of the current result (a plain link, not a
 * client-routed one, so nothing prefetches the file) and a way to the deadline calendar.
 */
export function ResultTools({ csvHref, calendarHref = '/calendar', className, total, status, atLeast }: {
  csvHref: string; calendarHref?: string; className?: string;
  /** How many rows the result has and its status filter: said when the file will hold fewer (site-qa2:N8). */
  total?: number; status?: string;
  /** The total is a lower bound (the count stopped at its cap): "at least". */
  atLeast?: boolean;
}) {
  const cap = exportCap(status, EXPORT_ROW_CAP);
  const cut = typeof total === 'number' && total > cap;
  // The tenders file marks a cut in a column (`result_truncated`); the funding file still ends with a note row.
  const tenders = csvHref.startsWith('/tenders/');
  return (
    <div className={cn('flex flex-col gap-2 rounded-lg border border-edge bg-surface p-5', className)}>
      <a href={csvHref} download className={cn(buttonVariants({ variant: 'secondary', fullWidth: true }))}>
        <Icon icon={Download} size="button" />Download CSV
      </a>
      <p className="m-0 text-small text-ink-muted">The public fields of this result, up to 2,000 rows (1,000 when the status is All), with source, licence and attribution on every row.</p>
      {cut && (
        <p className="m-0 text-small font-semibold text-ink">
          This result has {atLeast ? 'at least ' : ''}{total.toLocaleString('en-GB')} rows. {tenders
            ? <>The file holds the {cap.toLocaleString('en-GB')} most recently added, in the order you chose, and every row says <span className="font-mono">result_truncated = true</span>; narrow the filters to get the rest.</>
            : <>The file holds the first {cap.toLocaleString('en-GB')} and its last row says so; narrow the filters to get the rest.</>}
        </p>
      )}
      <Link href={calendarHref} className="inline-flex min-h-11 items-center gap-2 text-small font-bold">
        <Icon icon={CalendarDays} size="inline" />Deadline calendar
      </Link>
    </div>
  );
}
