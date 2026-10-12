import { cn } from '@/lib/utils';
import type { RunStatus, StatusKind } from '@/lib/types';

/** Non-interactive label. `programme` = pine fill + mono; `neutral` = inset fill. */
export function Tag({ kind = 'neutral', children }: { kind?: 'programme' | 'neutral'; children: React.ReactNode }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill px-2.5 py-[5px] text-label',
      kind === 'programme' ? 'bg-primary font-mono font-medium text-on-primary' : 'bg-surface-inset font-sans font-bold text-ink')}>
      {children}
    </span>
  );
}

const PILL: Record<StatusKind, { cls: string; label: string }> = {
  open: { cls: 'bg-open-bg text-open-fg', label: 'Open' },
  // Not time pressure: neutral inset fill with a hairline so it also reads on the page background.
  upcoming: { cls: 'border-line bg-surface-inset text-ink', label: 'Opens soon' },
  soon: { cls: 'bg-soon-bg text-soon-fg', label: 'Closing soon' },
  closed: { cls: 'bg-closed-bg text-closed-fg', label: 'Closed' },
  amended: { cls: 'bg-primary text-on-primary', label: 'Amended' },
  // Neither open nor closed: the source does not say. Neutral fill with a hairline, never the green of "Open".
  unknown: { cls: 'border-line bg-surface-inset text-ink', label: 'Status unknown' },
};

/** Always text-labelled, never colour alone. Not interactive. */
export function StatusPill({ status, children }: { status: StatusKind; children?: React.ReactNode }) {
  const p = PILL[status];
  return <span className={cn('inline-flex items-center whitespace-nowrap rounded-pill border border-transparent px-3 py-1.5 font-sans text-label', p.cls)}>{children ?? p.label}</span>;
}

const RUN_PILL: Record<RunStatus, { cls: string; label: string }> = {
  ok: { cls: 'border-transparent bg-open-bg text-open-fg', label: 'OK' },
  // A short run is not time pressure and not an error: neutral fill with a hairline.
  partial: { cls: 'border-line bg-surface-inset text-ink', label: 'Partial' },
  failed: { cls: 'border-alert bg-surface-inset text-alert', label: 'Failed' },
  never: { cls: 'border-transparent bg-closed-bg text-closed-fg', label: 'Never run' },
};

/** Result of a source's last collection run. Always text-labelled. Not interactive. */
export function RunStatusPill({ status }: { status: RunStatus }) {
  const p = RUN_PILL[status];
  return <span className={cn('inline-flex items-center whitespace-nowrap rounded-pill border px-3 py-1.5 font-sans text-label', p.cls)}>{p.label}</span>;
}
