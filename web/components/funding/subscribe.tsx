import { BellRing, CalendarDays, Download, Rss } from 'lucide-react';
import { FUNDING_FEED_MAX, fundingSubscription } from '@/lib/funding-feed';
import { SITE } from '@/lib/seo';
import type { CallFilters } from '@/lib/types';
import { Icon } from '../dg/icon';

const LINK = 'inline-flex min-h-11 items-center gap-2 text-small font-bold';

/**
 * WP-99 (p09): "Subscribe to this search" on /funding, as on /tenders (components/tenders/subscribe.tsx): the deadline calendar of the
 * search (webcal, or the file) and the Atom feed of its calls, each with exactly the list's filters. A native `details`, so it works
 * without script and by keyboard.
 */
export function SubscribeToFunding({ filters }: { filters: CallFilters }) {
  const s = fundingSubscription(filters, SITE.url);
  return (
    <details data-subscribe-funding className="group min-w-0 rounded-lg border border-line bg-surface px-5">
      <summary className="flex min-h-12 cursor-pointer items-center gap-2 py-2 text-body font-semibold">
        <Icon icon={BellRing} size="inline" />Subscribe to this search
      </summary>
      <div className="flex flex-col gap-3 pb-4 text-small">
        <p className="m-0 max-w-prose text-ink-muted">Both follow every filter you set here; change the filters and subscribe again for another search.</p>
        {s.webcal && s.ics && (
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap gap-x-6">
              <a href={s.webcal} className={LINK} data-subscribe-webcal><Icon icon={CalendarDays} size="inline" />Add the deadlines to your calendar</a>
              <a href={s.ics} download className={LINK} data-subscribe-ics><Icon icon={Download} size="inline" />Download the calendar file (.ics)</a>
            </div>
            <p className="m-0 max-w-prose text-ink-muted">
              The deadlines of the calls of this search, and the opening days of the ones not open yet, in UTC; your calendar app reads it
              again by itself. A call that states no deadline is not in it, and the file says how many.
            </p>
          </div>
        )}
        <div className="flex flex-col gap-1">
          <a href={s.atom} className={LINK} data-subscribe-atom><Icon icon={Rss} size="inline" />Atom feed of the calls of this search</a>
          <p className="m-0 max-w-prose text-ink-muted">
            The calls of this search, the newest first (up to {FUNDING_FEED_MAX}): a new call that matches shows as a new entry. Paste the
            address into a feed reader.
          </p>
        </div>
      </div>
    </details>
  );
}
