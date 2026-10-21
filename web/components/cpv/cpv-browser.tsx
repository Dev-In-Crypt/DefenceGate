'use client';

import { useId, useMemo, useState } from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { TextInput } from '../dg/form';
import { EmptyState } from '../dg/feedback';
import { Card } from '../dg/card';
import type { CpvSection } from '@/lib/cpv';

// Narrower steps on a phone: at 64 px a code of the fourth level had 160 px left for its title.
const INDENT = ['pl-0', 'pl-3 sm:pl-4', 'pl-6 sm:pl-12', 'pl-6 sm:pl-12', 'pl-8 sm:pl-16'] as const;

function matches(r: { code: string; title: string }, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (/^[\d\s-]+$/.test(q)) return r.code.startsWith(q.replace(/\D/g, ''));
  const title = r.title.toLowerCase();
  return q.split(/\s+/).every((w) => title.includes(w) || r.code.startsWith(w));
}

/**
 * The selection of CPV codes, in sections. Rendered in full on the server (so it is in the HTML); the search
 * box narrows it in the browser. Each code links to the tenders whose CPV codes start with its digits.
 */
export function CpvBrowser({ sections }: { sections: CpvSection[] }) {
  const [query, setQuery] = useState('');
  const resultsId = useId();
  const shown = useMemo(
    () => sections.map((s) => ({
      ...s,
      groups: s.groups.map((g) => ({ ...g, rows: g.rows.filter((r) => matches(r, query)) })).filter((g) => g.rows.length > 0),
    })).filter((s) => s.groups.length > 0),
    [sections, query],
  );
  const count = shown.reduce((n, s) => n + s.groups.reduce((m, g) => m + g.rows.length, 0), 0);
  const filtering = query.trim() !== '';

  return (
    <div className="flex flex-col gap-6">
      <div role="search" className="flex max-w-form flex-col gap-2">
        <TextInput search label="Search by code or words" placeholder="For example 3530 or ammunition" value={query}
          onChange={(e) => setQuery(e.target.value)} aria-controls={resultsId} autoComplete="off" />
        <p className="m-0 text-small text-ink-muted" aria-live="polite">
          {filtering ? `${count} ${count === 1 ? 'code matches' : 'codes match'}.` : 'Type digits to match the start of a code, or words to match the title.'}
        </p>
      </div>

      <div id={resultsId} className="flex flex-col gap-6">
        {count === 0 ? (
          <EmptyState title="No code in this selection matches">
            The finder holds a selection of the vocabulary, not all of it. A code that is not listed can still be used in a notice.
          </EmptyState>
        ) : shown.map((s) => (
          <Card key={s.id} title={s.title} id={`cpv-${s.id}`} headingLevel="h2">
            <p className="m-0 text-small text-ink-muted">{s.intro}</p>
            {s.groups.map((g) => (
              <div key={g.id} className="flex flex-col gap-1">
                {g.title && <h3 id={`cpv-${g.id}`} className="m-0 text-h4">{g.title}</h3>}
                {/* Two columns from lg: a section of fifty codes is a screen, not four. */}
                <ul className="m-0 list-none p-0 lg:columns-2 lg:gap-x-10" aria-labelledby={g.title ? `cpv-${g.id}` : undefined}>
                  {g.rows.map((r) => (
                    <li key={r.code} className={cn('break-inside-avoid border-t border-line', INDENT[Math.min(r.indent, 4)])}>
                      <Link href={`/tenders?cpv=${r.prefix}`}
                        className="grid min-h-10 grid-cols-[minmax(88px,auto)_minmax(0,1fr)] items-baseline gap-x-3 py-2 text-ink no-underline hover:underline">
                        <span className="font-mono text-mono-strong tabular-nums">{r.code}</span>
                        <span className={cn('min-w-0 break-words text-body', r.level <= 1 && 'font-semibold')}>{r.title}<span className="sr-only">: tenders with this code</span></span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </Card>
        ))}
      </div>
    </div>
  );
}
