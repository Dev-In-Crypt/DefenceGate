import Link from 'next/link';
import { TriangleAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { dayOf, groupByDay, monthWeeks, truncateTitle, type CalendarEntry } from '@/lib/calendar';
import { displayName } from '@/lib/display-name';
import { dayParts, formatDateUtc } from '@/lib/format';
import { Card } from '../dg/card';
import { Icon } from '../dg/icon';
import { Tag } from '../dg/tag';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;
const CELL_ENTRIES = 3;

/** "Tue 13 Oct 2026" for a `YYYY-MM-DD` key. */
export function dayLabel(day: string): string {
  const iso = `${day}T00:00:00Z`;
  return `${dayParts(iso).weekday} ${formatDateUtc(iso)}`;
}

function EntryRow({ e }: { e: CalendarEntry }) {
  return (
    <li className="group relative flex min-w-0 flex-col gap-1 border-t border-line py-3 first:border-t-0">
      <div className="flex flex-wrap items-center gap-2">
        <Tag kind={e.kind === 'tender' ? 'programme' : 'neutral'}>{e.kind === 'tender' ? 'Tender' : 'Funding call'}</Tag>
        {e.country && <Tag>{e.country}</Tag>}
        <span className="font-mono text-mono text-ink-muted">{e.when}</span>
      </div>
      <Link href={e.href}
        className="[overflow-wrap:anywhere] py-1 text-body font-semibold text-ink no-underline decoration-2 underline-offset-4 after:absolute after:inset-0 after:content-[''] group-hover:underline">
        {displayName(e.title)}
      </Link>
      <span className="[overflow-wrap:anywhere] text-small text-ink-muted">{displayName(e.who, 'title')} · {e.sourceName}</span>
      {e.note && (
        <p className="m-0 flex items-start gap-1.5 text-small text-ink-muted">
          <Icon icon={TriangleAlert} size="inline" className="mt-0.5 shrink-0" /><span>{e.note}</span>
        </p>
      )}
    </li>
  );
}

/**
 * Entries grouped by day, each day a card with the date in its own column (from lg) and the entries beside it: a day with one
 * deadline is one short row, not a full-width box. Every day has an anchor (`#d-YYYY-MM-DD`) the month grid links to.
 */
export function Agenda({ entries }: { entries: CalendarEntry[] }) {
  return (
    <div className="flex flex-col gap-4">
      {groupByDay(entries).map(({ day, items }) => (
        <Card key={day} anchor={`d-${day}`} id={`h-${day}`} headingLevel="h3" className="split scroll-mt-4 [&>.card-body]:pt-2 [&>.card-head]:min-h-0 [&>.card-head]:border-b-0 [&>.card-head]:pb-0 [&>.card-head]:pt-5"
          title={<time dateTime={day}>{dayLabel(day)}</time>}>
          <ul className="m-0 flex list-none flex-col p-0">
            {items.map((e) => <EntryRow key={e.key} e={e} />)}
          </ul>
        </Card>
      ))}
    </div>
  );
}

/**
 * The month as a table, Monday first, from md. Below md it is not shown and the agenda carries the same
 * entries. A cell lists up to three entries and links to the rest in the agenda under it.
 */
export function MonthGrid({ month, label, entries, today, moreHref }: {
  month: string; label: string; entries: CalendarEntry[]; today: string;
  /** Where "+N more" of a day leads: the agenda page that holds that day's entries (the agenda is paged). */
  moreHref?: (day: string) => string;
}) {
  const byDay = new Map<string, CalendarEntry[]>();
  for (const e of entries) {
    const k = dayOf(e.deadline);
    byDay.set(k, [...(byDay.get(k) ?? []), e]);
  }
  return (
    <div className="hidden rounded-lg border border-transparent bg-surface p-3 md:block">
      <table className="w-full table-fixed border-separate border-spacing-1">
        <caption className="sr-only">Deadlines in {label}, UTC</caption>
        <thead>
          <tr>{WEEKDAYS.map((d) => <th key={d} scope="col" className="px-2 py-1 text-left text-label text-ink-muted">{d}</th>)}</tr>
        </thead>
        <tbody>
          {monthWeeks(month).map((week, i) => (
            <tr key={i}>
              {week.map((day, j) => {
                if (!day) return <td key={j} className="rounded-md" aria-hidden="true" />;
                const items = byDay.get(day) ?? [];
                return (
                  <td key={day} className={cn('h-28 min-w-0 rounded-md bg-surface-inset p-1.5 align-top', day === today && 'outline outline-2 -outline-offset-2 outline-accent-text')}>
                    <div className="flex flex-col">
                      <span className="px-1 font-mono text-mono-strong tabular-nums">{Number(day.slice(8))}</span>
                      {items.slice(0, CELL_ENTRIES).map((e) => (
                        <Link key={e.key} href={e.href} title={displayName(e.title)}
                          aria-label={`${e.kind === 'tender' ? 'Tender' : 'Funding call'}: ${displayName(e.title)}`}
                          className="block min-h-8 [overflow-wrap:anywhere] rounded-md px-1 py-2 text-label text-ink">
                          {truncateTitle(displayName(e.title))}
                        </Link>
                      ))}
                      {items.length > CELL_ENTRIES && (
                        <a href={moreHref ? moreHref(day) : `#d-${day}`} className="block min-h-8 px-1 py-2 text-label">+{items.length - CELL_ENTRIES} more</a>
                      )}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
