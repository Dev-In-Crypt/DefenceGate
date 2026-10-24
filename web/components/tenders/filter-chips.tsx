import Link from 'next/link';
import { X } from 'lucide-react';
import { Icon } from '../dg/icon';
import { filterChips } from '@/lib/analyst';
import { now } from '@/lib/deadline';
import type { TenderFilters } from '@/lib/types';

/**
 * WP-98b (p02, phone): the filters of the list as chips above the results, each taking itself off. Below lg only: from lg the filter
 * column is beside the results and says the same.
 */
export function FilterChips({ filters, basePath }: { filters: TenderFilters; basePath: string }) {
  const chips = filterChips(filters, basePath, now());
  if (chips.length === 0) return null;
  return (
    <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0 lg:hidden" aria-label="Filters in use" data-filter-chips>
      {chips.map((c) => (
        <li key={c.label}>
          <Link href={c.href} className="inline-flex min-h-8 items-center gap-1 rounded-pill border border-line bg-surface px-3 text-small font-semibold text-ink">
            {c.label}<Icon icon={X} size="inline" /><span className="sr-only"> (remove this filter)</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
