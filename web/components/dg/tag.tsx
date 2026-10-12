import { cn } from '@/lib/utils';
import type { StatusKind } from '@/lib/types';

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
};

/** Always text-labelled, never colour alone. Not interactive. */
export function StatusPill({ status, children }: { status: StatusKind; children?: React.ReactNode }) {
  const p = PILL[status];
  return <span className={cn('inline-flex items-center whitespace-nowrap rounded-pill border border-transparent px-3 py-1.5 font-sans text-label', p.cls)}>{children ?? p.label}</span>;
}
