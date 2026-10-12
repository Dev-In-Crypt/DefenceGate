import Link from 'next/link';
import { CLASSIFIED_AUTOMATICALLY, basisChips, type BasisInput } from '@/lib/tender-basis';
import { cn } from '@/lib/utils';
import { Tag } from './tag';

/**
 * Why a notice is listed: the signals the API holds (legal basis, scope, buyer class, dual-use, clearance),
 * and a line that says the classification is automatic, linked to the methodology. On a card the link is
 * lifted above the stretched title link with `lifted`.
 */
export function BasisChips({ tender, lifted = false, className }: { tender: BasisInput; lifted?: boolean; className?: string }) {
  const chips = basisChips(tender);
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {chips.length > 0 && (
        <ul aria-label="Why this notice is listed" className="m-0 flex list-none flex-wrap gap-2 p-0">
          {chips.map((c) => <li key={c}><Tag wrap>{c}</Tag></li>)}
        </ul>
      )}
      <p className="m-0 text-small text-ink-muted">
        {CLASSIFIED_AUTOMATICALLY}; <Link href="/methodology" className={cn('font-semibold', lifted && 'relative z-10')}>see how</Link>
      </p>
    </div>
  );
}
