import { BellRing, CalendarDays, Download, Rss } from 'lucide-react';
import { CALENDAR_API_MAX, FEED_MAX, subscription } from '@/lib/analyst';
import { formatNumber } from '@/lib/format';
import { SITE } from '@/lib/seo';
import type { TenderFilters } from '@/lib/types';
import { Icon } from '../dg/icon';

const LINK = 'inline-flex min-h-11 items-center gap-2 text-small font-bold';

/**
 * WP-90: "Subscribe to this search", one control on /tenders: the deadline calendar (webcal, or the file) and the Atom feed of new
 * notices and changes, each with exactly the list's filters (lib/analyst.ts `subscription`). A native `details`, so it works without
 * script and by keyboard; the ceilings are said here and, when they cut, in the file itself.
 */
export function SubscribeToSearch({ filters }: { filters: TenderFilters }) {
  const s = subscription(filters, SITE.url);
  return (
    <details data-subscribe className="group min-w-0 rounded-lg border border-line bg-surface px-5">
      <summary className="flex min-h-12 cursor-pointer items-center gap-2 py-2 text-body font-semibold">
        <Icon icon={BellRing} size="inline" />Subscribe to this search
      </summary>
      <div className="flex flex-col gap-3 pb-4 text-small">
        <p className="m-0 max-w-prose text-ink-muted">Both follow every filter you set here; change the filters and subscribe again for another search.</p>
        <div className="flex flex-col gap-1">
          {s.webcal && s.ics ? (
            <>
              <div className="flex flex-wrap gap-x-6">
                <a href={s.webcal} className={LINK} data-subscribe-webcal><Icon icon={CalendarDays} size="inline" />Add the deadlines to your calendar</a>
                <a href={s.ics} download className={LINK} data-subscribe-ics><Icon icon={Download} size="inline" />Download the calendar file (.ics)</a>
              </div>
              <p className="m-0 max-w-prose text-ink-muted" data-subscribe-cap>
                The open tenders of this search that state a deadline, soonest first, in UTC; your calendar app reads it again by itself. At
                most {formatNumber(CALENDAR_API_MAX)} tenders, and deadlines more than three years ahead (frameworks) are left out: the file
                says so when either happens.
              </p>
            </>
          ) : (
            <p className="m-0 max-w-prose text-ink-muted" data-subscribe-cap>A calendar holds open tenders only: choose the status Open or All for one.</p>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <a href={s.atom} className={LINK} data-subscribe-atom><Icon icon={Rss} size="inline" />Atom feed of new tenders and changes</a>
          <p className="m-0 max-w-prose text-ink-muted">
            New tenders and moved deadlines, values, statuses and procedures of the last 14 days, for this search with its status as it is
            today; the newest {formatNumber(FEED_MAX)} entries, and the older ones on the feed&rsquo;s next pages (the feed says how many there are). Its
            name in your reader is this search. Paste the address into a
            feed reader.
          </p>
        </div>
      </div>
    </details>
  );
}
