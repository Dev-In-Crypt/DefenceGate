import Link from 'next/link';
import { CLASSIFIED_AUTOMATICALLY, CONFIDENCE_HREF, WHY_HERE, basisChips, confidenceView, type BasisInput, type ConfidenceView } from '@/lib/tender-basis';
import { cn } from '@/lib/utils';
import { Tag } from './tag';

/**
 * How sure we are, as a word: High is the strong neutral (ink border), Medium the plain one, Low muted and dashed.
 * Never a colour alone and never a traffic light. The reason shows on hover and on keyboard focus; the accessible
 * name carries the level and the reason, so a screen reader needs neither.
 */
const LEVEL_CLASS: Record<ConfidenceView['level'], string> = {
  high: 'border-ink bg-surface-inset font-bold text-ink',
  medium: 'border-line bg-surface-inset font-bold text-ink',
  low: 'border-dashed border-line bg-transparent font-semibold text-ink-muted',
};

function ConfidenceBadge({ view, lifted }: { view: ConfidenceView; lifted: boolean }) {
  return (
    <span className={cn('group/conf inline-flex', lifted && 'relative z-10')}>
      <span
        tabIndex={0}
        role="note"
        aria-label={view.name}
        data-confidence={view.level}
        className={cn('relative inline-flex cursor-help items-center whitespace-nowrap rounded-pill border px-2.5 py-[4px] text-label', LEVEL_CLASS[view.level])}
      >
        {view.text}
        {view.sentence && (
          <span
            aria-hidden="true"
            className="hidden absolute left-0 top-full z-20 mt-1 w-72 max-w-[calc(100vw-4rem)] whitespace-normal rounded-lg border border-edge bg-surface px-3 py-2 text-small font-normal text-ink shadow-lg group-focus-within/conf:block group-hover/conf:block"
          >
            {view.sentence}
          </span>
        )}
      </span>
    </span>
  );
}

/**
 * Why a notice is listed: the signals the API holds (legal basis, scope, buyer class, dual-use, clearance), how
 * sure we are, and a line that says the classification is automatic, linked to the methodology. On a card the links
 * are lifted above the stretched title link with `lifted`.
 */
export function BasisChips({ tender, lifted = false, className, note = true }: {
  tender: BasisInput; lifted?: boolean; className?: string;
  /** The "Classified automatically ... see how" line. A list says it once for all its cards (`ClassifiedNote`) and passes false. */
  note?: boolean;
}) {
  const chips = basisChips(tender);
  const confidence = confidenceView(tender.confidence);
  if (!note && chips.length === 0 && !confidence) return null;
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      {(chips.length > 0 || confidence) && (
        <div className="flex flex-wrap items-center gap-2">
          {chips.length > 0 && (
            <>
              <span className="text-label text-ink-muted">{WHY_HERE}</span>
              <ul aria-label="Why this notice is listed" className="m-0 flex list-none flex-wrap gap-2 p-0">
                {chips.map((c) => <li key={c}><Tag wrap>{c}</Tag></li>)}
              </ul>
            </>
          )}
          {confidence && <ConfidenceBadge view={confidence} lifted={lifted} />}
        </div>
      )}
      {note && <ClassifiedLine confidence={Boolean(confidence)} lifted={lifted} />}
    </div>
  );
}

function ClassifiedLine({ confidence, lifted = false }: { confidence: boolean; lifted?: boolean }) {
  return (
    <p className="m-0 text-small text-ink-muted">
      {CLASSIFIED_AUTOMATICALLY}{confidence ? ', with how sure we are estimated from checked samples' : ''}; <Link href={confidence ? CONFIDENCE_HREF : '/methodology'} className={cn('font-semibold', lifted && 'relative z-10')}>see how</Link>
    </p>
  );
}

/** The same line, once, above a list of notices whose cards do not repeat it. */
export function ClassifiedNote({ tenders, className }: { tenders: BasisInput[]; className?: string }) {
  return <div className={className}><ClassifiedLine confidence={tenders.some((t) => confidenceView(t.confidence))} /></div>;
}
