'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { CircleAlert, CircleCheck, CircleHelp, CircleX } from 'lucide-react';
import { fitLabel, fitOrder, shownFit, topicsLine } from '@/lib/fit';
import { useFit, useFitState } from '@/lib/fit-hooks';
import { fitFor, hiddenByFilter, isLoaded, lookupFailed, refresh, setOnlyFits, topicsMatched } from '@/lib/fit-store';
import { useProfile } from '@/components/readiness/use-readiness';
import { cn } from '@/lib/utils';
import { Choice, TextInput } from '../dg/form';
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
  const result = fitFor(id);
  // WP-102: a failed look-up is not "rules not read"
  const { word, detail } = lookupFailed(id) ? { word: 'Not compared yet: reload the page', detail: 'The rules of this call could not be loaded just now.' } : fitLabel(result);
  return (
    <span title={detail}
      className={cn('inline-flex max-w-full items-start gap-1.5 rounded-pill border border-line bg-surface-inset px-2.5 py-[5px] font-sans text-label text-ink', className)}>
      <Icon icon={ICON[shownFit(result)]} size="inline" className="mt-0.5 shrink-0" />
      <span className="sr-only">Your saved profile: </span>
      <span className="min-w-0 break-words">{word}</span>
    </span>
  );
}

/**
 * A list item that "Fits my profile" can hide. Server-rendered children, so the list itself stays a server page. WP-91: with the filter
 * on and topics in the saved profile, a call that holds more of them comes first (CSS `order` in the list's flex column: the server's
 * order is kept for the rest), and says which.
 */
export function FitItem({ id, children, className, text = '' }: { id: string; children: React.ReactNode; className?: string; text?: string }) {
  const s = useFit(id);
  const matched = s.onlyFits && s.hasProfile ? topicsMatched(s, text) : 0;
  // WP-102 (p05): with the filter on, the calls with the visitor's topics first, the eligible ones of them first; a call that needs a
  // partner the profile says it lacks, or that others join only as partners, after the rest
  const order = s.onlyFits && s.hasProfile && isLoaded(id) ? fitOrder(fitFor(id), matched) : 0;
  return (
    <li hidden={hiddenByFilter(s, id)} className={className} style={order !== 0 ? { order } : undefined} data-topics-matched={matched || undefined} data-fit-order={order || undefined}>
      {matched > 0 && <p className="m-0 mb-1 text-small font-bold text-ink">{topicsLine(matched, s.topics.length)}</p>}
      {children}
    </li>
  );
}

/** WP-91: the company's topics, kept in the saved profile in this browser (never sent): the order of "Fits my profile". */
function Topics() {
  const { profile, ready, update } = useProfile();
  if (!ready || !profile) return null;
  return (
    <TextInput label="Your topics (optional)" maxLength={300} className="max-w-form" value={profile.topics}
      placeholder="For example: software, autonomy, counter-drone"
      hint="Comma-separated. Kept with your profile in this browser only. Matched like the search: drone also finds unmanned, software also finds algorithms."
      onChange={(e) => { update((p) => ({ ...p, topics: e.target.value })); window.setTimeout(refresh, 0); }} />
  );
}

/**
 * WP-99: on a paged list the filter works over the whole result, not one page: switched on, it opens the same search with every call on one
 * page (`fit=1`, at most the API's 500), and the topics rank all of them. `on` is that page; the two links are the search with and without it.
 */
export interface WholeList { on: boolean; onHref: string; offHref: string; total: number }

/**
 * The switch "Fits my profile": keep the calls that are eligible or worth a look, hide the ones that are not eligible and the ones whose
 * rules were not read, and say how many it hides. With `whole` (the funding list) it works over every call of the search; without it
 * (the digest, the change feed: one page each) over what is on the page. Not shown without a saved profile, with a link to the readiness
 * check instead.
 */
export function FitFilter({ className, whole }: { className?: string; whole?: WholeList }) {
  const s = useFitState();
  const router = useRouter();
  // the page of every call is the filter switched on: it is on there, whatever the last page left it
  useEffect(() => { if (whole?.on) setOnlyFits(true); }, [whole?.on]);
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
      <Choice label="Fits my profile" checked={s.onlyFits} onChange={(e) => {
        setOnlyFits(e.target.checked);
        if (whole && e.target.checked !== whole.on) router.push(e.target.checked ? whole.onHref : whole.offHref, { scroll: false });
      }}
        hint={`Keeps the calls ${whole ? 'of this search' : 'on this page'} that are eligible or where nothing known blocks you, judged on the rules read from each call’s document and, for EDF and EDIP calls, on the programme’s rules. Hides the blocked ones and the ones without rules. With your topics below, the calls that name them come first${whole ? ', across the whole list' : ''}, the eligible ones of them first; calls that need a partner you said you lack, or that others join only as partners, come last.`} />
      <Topics />
      <p role="status" className="m-0 text-small text-ink-muted">
        {s.loaded === 0 ? `Checking the calls ${whole?.on ? 'of this search' : 'on this page'}…` : (
          <>
            {whole?.on ? `Of the ${whole.total} calls of this search` : 'On this page'}: {s.counts.yes} eligible on the rules read, {s.counts.check} where nothing known blocks you but conditions are left to check,
            {' '}{s.counts.no} blocked, {s.counts.unknown} without rules to compare.
            {s.onlyFits && hidden > 0 ? ` ${hidden} hidden.` : ''}
          </>
        )}
      </p>
    </div>
  );
}
