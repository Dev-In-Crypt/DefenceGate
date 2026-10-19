import { TriangleAlert } from 'lucide-react';
import { Icon } from './icon';

/**
 * Parameters of a list URL that were not used (lib/filters.ts ignoredFilters), shown above the results so a
 * mistyped link is not read as "there are no results". Renders nothing when there are none.
 */
export function FilterNotices({ notices }: { notices: string[] }) {
  if (notices.length === 0) return null;
  return (
    <div role="status" className="flex max-w-prose flex-col gap-1 rounded-md bg-surface-inset px-4 py-3 text-small text-ink">
      {notices.map((n) => (
        <p key={n} className="m-0 flex items-start gap-1.5"><Icon icon={TriangleAlert} size="inline" className="mt-0.5 shrink-0" /><span>{n}</span></p>
      ))}
    </div>
  );
}
