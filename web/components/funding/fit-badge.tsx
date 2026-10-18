'use client';

import Link from 'next/link';
import { CircleAlert, CircleCheck, CircleHelp, CircleX } from 'lucide-react';
import { FIT_MEANING, FIT_WORD } from '@/lib/fit';
import { fitFor, hiddenByFilter, isLoaded, setOnlyFits, useFit, useFitState } from '@/lib/fit-store';
import { cn } from '@/lib/utils';
import { Choice } from '../dg/form';
import { Icon } from '../dg/icon';

/**
 * The fit of one call to the profile saved in this browser (WP-32). Nothing is rendered on the server or for a
 * visitor without a profile: the page and its cache are the same for everybody, and a visitor without a profile
 * causes no request. The word and the icon carry the meaning; colour only repeats it.
 */
const ICON = { yes: CircleCheck, check: CircleAlert, no: CircleX, unknown: CircleHelp } as const;

export function FitBadge({ id, className }: { id: string; className?: string }) {
  const s = useFit(id);
  if (!s.ready || !s.hasProfile || !isLoaded(id)) return null;
  const { fit, conditions } = fitFor(id);
  return (
    <span title={[FIT_MEANING[fit], ...(fit === 'unknown' ? [] : conditions)].join(' ')}
      className={cn('inline-flex items-center gap-1.5 rounded-pill border border-line bg-surface-inset px-2.5 py-[5px] font-sans text-label text-ink', className)}>
      <Icon icon={ICON[fit]} size="inline" />
      <span className="sr-only">Your saved profile: </span>
      <span>{FIT_WORD[fit]}</span>
    </span>
  );
}

/** A list item that "Fits my profile" can hide. Server-rendered children, so the list itself stays a server page. */
export function FitItem({ id, children, className }: { id: string; children: React.ReactNode; className?: string }) {
  const s = useFit(id);
  return <li hidden={hiddenByFilter(s, id)} className={className}>{children}</li>;
}

/**
 * The switch "Fits my profile": keep the calls of this page that are eligible or worth a look, hide the ones that are
 * not eligible and the ones whose rules were not read. It filters what is on the page, and says how many it hides.
 * Not shown without a saved profile, with a link to the readiness check instead.
 */
export function FitFilter({ className }: { className?: string }) {
  const s = useFitState();
  if (!s.ready) return null;
  if (!s.hasProfile) {
    return (
      <p className={cn('m-0 text-small text-ink-muted', className)}>
        <Link href="/readiness" className="font-semibold">Answer the readiness check</Link> to see which of these calls fit your company. Your answers stay in your browser.
      </p>
    );
  }
  const hidden = s.counts.no + s.counts.unknown;
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <Choice label="Fits my profile" checked={s.onlyFits} onChange={(e) => setOnlyFits(e.target.checked)}
        hint="Keeps the calls on this page that are eligible or worth a look, judged on the rules read from each call’s document and, for EDF and EDIP calls, on the programme’s rules." />
      <p role="status" className="m-0 text-small text-ink-muted">
        {s.loaded === 0 ? 'Checking the calls on this page…' : (
          <>
            On this page: {s.counts.yes} eligible, {s.counts.check} to check, {s.counts.no} not eligible, {s.counts.unknown} without rules to compare.
            {s.onlyFits && hidden > 0 ? ` ${hidden} hidden.` : ''}
          </>
        )}
      </p>
    </div>
  );
}
