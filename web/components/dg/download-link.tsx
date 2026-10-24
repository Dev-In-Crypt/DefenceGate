import Link from 'next/link';
import { CalendarDays, Download, Rss } from 'lucide-react';
import { cn } from '@/lib/utils';
import { exportCap, EXPORT_ROW_CAP } from '@/lib/export-cache';
import { MARKET_FIRST_YEAR } from '@/lib/filters';
import { now } from '@/lib/deadline';
import { buttonVariants } from './button';
import { Icon } from './icon';

/** The years a tender file can be asked for, newest first: the archive holds notices from 2021 (MARKET_FIRST_YEAR). */
function publicationYears(): number[] {
  const year = now().getUTCFullYear();
  return Array.from({ length: year - MARKET_FIRST_YEAR + 1 }, (_, i) => year - i);
}

/**
 * The tools of a result list, under the filters: the CSV of the current result (a plain link, not a
 * client-routed one, so nothing prefetches the file) and a way to the deadline calendar.
 */
export function ResultTools({ csvHref, calendarHref = '/calendar', feedHref, icsHref, className, total, status, atLeast }: {
  csvHref: string; calendarHref?: string; className?: string;
  /** WP-91: the calendar file of exactly this result (the funding search's /funding.ics). */
  icsHref?: string;
  /** WP-87: the Atom feed of the changes of this result (the list's filters travel with it). */
  feedHref?: string;
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
    <div className={cn('flex flex-col gap-2 rounded-lg border border-transparent bg-surface p-5', className)}>
      <a href={csvHref} download className={cn(buttonVariants({ variant: 'secondary', fullWidth: true }))}>
        <Icon icon={Download} size="button" />Download CSV
      </a>
      <p className="m-0 text-small text-ink-muted">The public fields of this result, up to 2,000 rows (1,000 when the status is All), with source, licence and attribution on every row.</p>
      {cut && (
        <p className="m-0 text-small font-semibold text-ink">
          This result has {atLeast ? 'at least ' : ''}{total.toLocaleString('en-GB')} rows. {tenders
            ? <>The file holds the {cap.toLocaleString('en-GB')} most recently added, in the list&rsquo;s order, and every row says <span className="font-mono">result_truncated = true</span>; its <span className="font-mono">Link</span> header is the address of the next part. Or take it a year of publication at a time:</>
            : <>The file holds the first {cap.toLocaleString('en-GB')} and its last row says so; narrow the filters to get the rest.</>}
        </p>
      )}
      {/* WP-100: a long tender result a year of publication at a time (`publishedFrom`/`publishedTo`), never only its newest rows */}
      {cut && tenders && (
        <ul className="m-0 flex list-none flex-wrap gap-x-4 p-0" data-csv-years>
          {publicationYears().map((y) => (
            <li key={y}>
              <a href={`${csvHref}${csvHref.includes('?') ? '&' : '?'}publishedFrom=${y}-01-01&publishedTo=${y}-12-31`} download
                className="inline-flex min-h-11 items-center gap-1 text-small font-bold"><Icon icon={Download} size="inline" />{y}</a>
            </li>
          ))}
        </ul>
      )}
      <Link href={calendarHref} className="inline-flex min-h-11 items-center gap-2 text-small font-bold">
        <Icon icon={CalendarDays} size="inline" />Deadline calendar of this search
      </Link>
      {icsHref && (
        <a href={icsHref} className="inline-flex min-h-11 items-center gap-2 text-small font-bold" data-search-ics>
          <Icon icon={CalendarDays} size="inline" />Calendar file of this search (.ics)
        </a>
      )}
      {feedHref && (
        <a href={feedHref} className="inline-flex min-h-11 items-center gap-2 text-small font-bold">
          <Icon icon={Rss} size="inline" />Changes of this search (Atom feed)
        </a>
      )}
    </div>
  );
}
