import { cn } from '@/lib/utils';
import { getDeadline, now, type DeadlineInfo } from '@/lib/deadline';
import { openingPhrase } from '@/lib/format';
import type { DeadlineState, IsoDateTime } from '@/lib/types';

const TONE: Record<DeadlineState, { box: string; label: string; count: string; date: string }> = {
  normal: { box: 'bg-surface-inset', label: 'text-ink-muted', count: 'text-accent-text', date: 'text-ink' },
  soon: { box: 'bg-soon-bg', label: 'text-soon-fg', count: 'text-soon-fg', date: 'text-soon-fg' },
  urgent: { box: 'bg-urgent', label: 'text-on-urgent', count: 'text-on-urgent', date: 'text-on-urgent' },
  closed: { box: 'bg-closed-bg', label: 'text-closed-fg', count: 'text-closed-fg', date: 'text-closed-fg' },
  // No stated deadline: neutral, no countdown, no time pressure.
  none: { box: 'bg-surface-inset', label: 'text-ink-muted', count: 'text-ink', date: 'text-ink' },
};

/**
 * The hero element: countdown in days + absolute UTC date, styled by deadline state.
 * `size="lg"` is the detail-page variant.
 * `opening` (forthcoming calls only): the opening date leads and the deadline, if any, follows it.
 * A null deadline renders "No fixed deadline" with no countdown.
 */
export function DeadlineBadge({ deadline, info, opening, size = 'md', className, local }: {
  deadline?: IsoDateTime | null; info?: DeadlineInfo; opening?: IsoDateTime | null; size?: 'md' | 'lg'; className?: string;
  /** The same moment in the buyer's own time zone (lib/deadline.ts localDeadline), where it adds something. */
  local?: string | null;
}) {
  const d = info ?? getDeadline(deadline ?? null);
  const t = TONE[d.state];
  const lg = size === 'lg';
  const dateSize = lg ? 'text-h2' : 'text-h3 tracking-[-0.5px]';

  if (opening) {
    return (
      <div data-deadline="" className={cn('inline-flex min-w-40 flex-col gap-1 rounded-md bg-surface-inset p-4', className)}>
        <span className="text-label text-ink-muted">{openingPhrase(opening, now()).lead}</span>
        <span className={cn('font-sans font-extrabold text-ink', dateSize)}>
          <time dateTime={opening}>{openingPhrase(opening, now()).date}</time>
        </span>
        <span className={cn('font-mono tabular-nums text-ink-muted', lg ? 'text-mono' : 'text-[12px] leading-4')}>
          {d.iso ? <>Deadline <time dateTime={d.iso}>{d.utc}</time></> : 'No fixed deadline'}
        </span>
      </div>
    );
  }

  if (d.state === 'none') {
    return (
      <div data-deadline="" className={cn('inline-flex min-w-40 flex-col gap-1 rounded-md p-4', t.box, className)}>
        <span className={cn('text-label', t.label)}>Deadline</span>
        <span className={cn('font-sans font-extrabold', dateSize, t.count)}>{d.label}</span>
      </div>
    );
  }

  if (d.rolling) {
    // Open past its last cut-off: the call takes submissions continuously or in several cut-offs.
    return (
      <div data-deadline="" className={cn('inline-flex min-w-40 flex-col gap-1 rounded-md p-4', t.box, className)}>
        <span className={cn('text-label', t.label)}>Submission</span>
        <span className={cn('font-sans font-extrabold', lg ? 'text-h2' : 'text-h3 tracking-[-0.5px]', t.count)}>{d.label}</span>
        <span className={cn('font-mono tabular-nums', lg ? 'text-mono-strong' : 'text-[12px] leading-4', t.date)}>
          Last cut-off <time dateTime={d.iso ?? undefined}>{d.utc}</time>
        </span>
      </div>
    );
  }

  // A closed deadline reads "Deadline / Closed / 27 Jul 2026": the word "Closed" is said once.
  const heading = d.state === 'closed' ? 'Deadline' : d.label;
  return (
    <div data-deadline="" className={cn('inline-flex min-w-40 flex-col gap-1 rounded-md p-4', t.box, className)}>
      <span className={cn('text-label', t.label)}>{heading}</span>
      <span className={cn('font-sans font-extrabold', lg ? 'text-h1' : 'text-[24px] leading-[30px] tracking-[-0.5px]', t.count)}>
        <time dateTime={d.iso ?? undefined}>{d.countdown}</time>
      </span>
      {d.utc && <span className={cn('font-mono tabular-nums', lg ? 'text-mono-strong' : 'text-[12px] leading-4', t.date)}>{d.utc}</span>}
      {/* The source gives a day. What time that day ends is in its call text, so say that and no more. */}
      {d.dateOnly && d.state !== 'closed' && <span className={cn('font-sans', lg ? 'text-small' : 'text-[12px] leading-4', t.label)}>Time not published by the source</span>}
      {local && <span className={cn('font-sans', lg ? 'text-small' : 'text-[12px] leading-4', t.label)}>{local}</span>}
    </div>
  );
}
