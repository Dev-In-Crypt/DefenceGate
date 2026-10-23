import Link from 'next/link';
import { Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Details } from './details';
import { Icon } from './icon';

/**
 * WP-88: what explains coverage, method, caveats, licences or confidence sits here, collapsed, so a page opens with one sentence and then
 * its list, form or table. A native `details` (keyboard and screen reader work without script); the public layout's PrintOpenDetails
 * and the print CSS open it on paper. `data-about` marks it for the e2e checks (present, closed by default).
 */
export function AboutData({ summary = 'About this data', children, className }: {
  summary?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <div data-about className={cn('min-w-0', className)}>
      <Details summary={summary}>{children}</Details>
    </div>
  );
}

/** An (i) link to a glossary entry beside a term: 24 px target, named for a screen reader. Every `id` must exist in lib/glossary.ts. */
export function InfoLink({ id, term, className }: { id: string; term: string; className?: string }) {
  return (
    <Link href={`/glossary#${id}`} aria-label={`What “${term}” means`} title={`What “${term}” means`}
      className={cn('inline-flex min-h-6 min-w-6 items-center justify-center align-middle text-link', className)}>
      <Icon icon={Info} size="inline" aria-hidden />
    </Link>
  );
}
