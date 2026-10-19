'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

export interface EntryItem { code: string; status: string; node: React.ReactNode }
export interface StatusChip { status: string; label: string; count: number }

/**
 * The entries of the tracker with a row of status chips above them. Every entry is in the page whatever the chip: the filter only
 * hides (the `hidden` attribute), so search, print and the permalink anchors see all of them, and the first view shows all of them.
 * A link to one entry (`#code`) clears the filter, so the entry it points at is never hidden.
 */
export function EntryList({ chips, items }: { chips: StatusChip[]; items: EntryItem[] }) {
  const [status, setStatus] = useState<string | null>(null);
  useEffect(() => {
    const clear = () => setStatus(null);
    window.addEventListener('hashchange', clear);
    return () => window.removeEventListener('hashchange', clear);
  }, []);
  const total = items.length;
  const shown = status ? items.filter((i) => i.status === status).length : total;
  return (
    <div className="flex flex-col gap-4">
      <div role="group" aria-label="Show entries by status" className="flex flex-wrap items-center gap-2">
        {[{ status: null as string | null, label: 'All', count: total }, ...chips].map((c) => (
          <button key={c.status ?? 'all'} type="button" aria-pressed={status === c.status} onClick={() => setStatus(c.status)}
            className={cn('inline-flex min-h-11 items-center gap-2 rounded-pill border px-4 text-small font-bold',
              status === c.status ? 'border-primary bg-primary text-on-primary' : 'border-edge bg-surface text-ink hover:bg-surface-inset')}>
            {c.label}<span className={cn('font-mono tabular-nums', status === c.status ? 'text-on-primary' : 'text-ink-muted')}>{c.count}</span>
          </button>
        ))}
        <p role="status" className="m-0 ml-1 text-small text-ink-muted">{status ? `Showing ${shown} of ${total} entries.` : ''}</p>
      </div>
      <ol className="m-0 flex list-none flex-col gap-4 p-0">
        {items.map((i) => (
          <li key={i.code} id={i.code} hidden={status !== null && i.status !== status}
            className={cn('grid min-w-0 scroll-mt-4 gap-x-10 gap-y-4 rounded-lg border border-edge bg-surface p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_460px]',
              status !== null && i.status !== status && 'hidden')}>
            {i.node}
          </li>
        ))}
      </ol>
    </div>
  );
}
