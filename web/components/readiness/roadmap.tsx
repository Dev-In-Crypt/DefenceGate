'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Check, Play } from 'lucide-react';
import { countryName } from '@/lib/taxonomy';
import { answerProblems, withStatus, type Profile } from '@/lib/profile';
import { CATEGORY_WORD, costHeadline, formatDays, formatRange, isoDay, joinWords, programmeName, requirementSlug, timeHeadline } from '@/lib/readiness';
import type { Roadmap, RoadmapStep, RoadmapTotals } from '@/lib/readiness-types';
import { safeHttpUrl } from '@/lib/safe-url';
import { Button } from '@/components/dg/button';
import { Callout } from '@/components/dg/blocks';
import { EmptyState, ErrorState, Skeleton } from '@/components/dg/feedback';
import { AutoGrid } from '@/components/dg/auto-grid';
import { AnswerProblems, NoProfile } from './results';
import { useAssessment, useProfile } from './use-readiness';

/** `steps`: how many steps the figures are over; `noCost` and `noTime`: how many of them state none (T7: the headline never reads as a complete or free plan when some do not). */
function Totals({ title, totals, id, steps, noCost, noTime }: { title: string; totals: RoadmapTotals; id: string; steps: number; noCost: number; noTime: number }) {
  const cost = costHeadline(totals, steps, noCost);
  return (
    <div className="flex flex-col gap-1 rounded-md bg-surface-inset p-4" data-totals={id}>
      <h3 className="m-0 text-body font-bold">{title}</h3>
      <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-body">
        <dt className="text-ink-muted">Cost</dt><dd className="m-0 font-mono tabular-nums">{cost}</dd>
        <dt className="text-ink-muted">Time</dt>
        <dd className="m-0 font-mono tabular-nums">{timeHeadline(totals.days, steps, noTime)}</dd>
      </dl>
    </div>
  );
}

function StepCard({ s, country, onMark }: { s: RoadmapStep; country: string; onMark: (code: string, status: 'held' | 'in_progress') => void }) {
  const blocking = s.blockingFor.length > 0;
  return (
    <li className="flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5" data-step={s.code}>
      <div className="flex flex-wrap items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-pill bg-primary font-mono text-mono-strong text-on-primary" aria-hidden="true">{s.order}</span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          {/* tabIndex -1: after a step is marked, focus moves to the heading of the step that takes its place (WP-53) */}
          <h3 tabIndex={-1} data-step-heading={s.code} className="m-0 text-h4"><span className="sr-only">Step {s.order}: </span>{s.name}</h3>
          <p className="m-0 flex flex-wrap gap-x-3 text-small text-ink-muted">
            <span>{CATEGORY_WORD[s.category] ?? s.category}</span>
            {s.status === 'in_progress' && <span className="font-bold text-ink">In progress</span>}
            {s.optional ? <span className="font-bold text-ink">Only {s.when}</span> : blocking ? <span className="font-bold text-ink">Needed now</span> : <span className="font-bold text-ink">Needed if you do what the rule describes</span>}
          </p>
        </div>
      </div>
      <p className="m-0 max-w-prose text-body text-ink-muted">{s.summary}</p>

      <dl className="m-0 grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1 rounded-md bg-surface-inset p-3">
          <dt className="text-label text-ink-muted">Cost</dt>
          <dd className="m-0 flex flex-col gap-0.5 text-body">
            <span className="font-mono tabular-nums">{formatRange(s.cost)}</span>
            {s.cost?.label && <span className="text-small font-bold">{s.cost.label}</span>}
          </dd>
        </div>
        <div className="flex flex-col gap-1 rounded-md bg-surface-inset p-3">
          <dt className="text-label text-ink-muted">Time</dt>
          <dd className="m-0 font-mono text-body tabular-nums">{formatDays(s.days)}</dd>
        </div>
      </dl>
      {s.priceNote && <p className="m-0 text-small font-bold">{s.priceNote}</p>}
      {s.branchNote && <p className="m-0 text-small">{s.branchNote}</p>}

      <div className="flex flex-col gap-1 text-body">
        <p className="m-0 font-bold">Issued by</p>
        {s.issuers.length > 0 ? (
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {s.issuers.map((i) => (
              <li key={i.name} className="flex flex-col text-body">
                <span>
                  {i.country !== '*' && <><abbr title={countryName(i.country)} className="font-mono no-underline">{i.country}</abbr>{' '}</>}
                  {safeHttpUrl(i.url) ? <a href={i.url as string} target="_blank" rel="noopener noreferrer">{i.name}</a> : i.name}
                </span>
                {i.notes && <span className="text-small text-ink-muted">{i.notes}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-small text-ink-muted">{s.issuerNote ?? `The body that issues this in ${countryName(country)} has not been collected.`}</p>
        )}
      </div>

      {s.neededFor.filter((n) => n.rule).length > 0 && (
        s.optional ? (
          // An optional step is a contract matter, not an eligibility condition: the line must not say the programme asks for it (U8).
          <p className="m-0 text-small text-ink-muted">
            Named by contracts under {joinWords([...new Set(s.neededFor.filter((n) => n.rule).map((n) => programmeName(n.programme)))])}. Whether you need it depends on the contract that names it; it is not a condition for applying to a programme.
          </p>
        ) : (
          <p className="m-0 text-small text-ink-muted">Asked by: {s.neededFor.filter((n) => n.rule).map((n) => `${programmeName(n.programme)} (${n.title})`).join('; ')}</p>
        )
      )}
      {s.prerequisites.length > 0 && (
        <p className="m-0 text-small text-ink-muted">
          {s.prerequisites.map((p) => (
            <span key={p.code} className="block">
              {p.relation === 'before' ? 'Comes after' : 'Before or together with'} {p.step ? `step ${p.step}, ` : ''}{p.name}
              {p.status === 'held' ? ' (you hold it)' : ''}.
            </span>
          ))}
        </p>
      )}
      {s.parallelWith.length > 0 && <p className="m-0 text-small text-ink-muted">Can run in parallel with step{s.parallelWith.length > 1 ? 's' : ''} {s.parallelWith.join(', ')}.</p>}

      <div className="flex flex-wrap items-center gap-3">
        {s.status !== 'in_progress' && <Button variant="secondary" icon={Play} onClick={() => onMark(s.code, 'in_progress')} aria-label={`Mark as started: ${s.name}`}>Mark as started</Button>}
        <Button variant="secondary" icon={Check} onClick={() => onMark(s.code, 'held')} aria-label={`Mark as done: ${s.name}`} data-mark-done={s.code}>Mark as done</Button>
        <Link href={`/requirements/${requirementSlug(s.code)}`} aria-label={`What is ${s.name}?`} className="inline-flex min-h-11 items-center text-small font-semibold">What is this?</Link>
        <span className="text-small text-ink-muted">Reviewed {isoDay(s.lastReviewed)}</span>
      </div>
    </li>
  );
}

function RoadmapBody({ plan, profile, onMark }: { plan: Roadmap; profile: Profile; onMark: (code: string, status: 'held' | 'in_progress') => void }) {
  const byCode = new Map(plan.steps.map((s) => [s.code, s]));
  if (plan.steps.length === 0) {
    return (
      <div data-roadmap-empty>
        <EmptyState title="Nothing left to obtain" action={<Button href="/readiness/results" iconRight={ArrowRight}>Back to my results</Button>}>
          On your answers, no requirement is missing. Your results page still lists what each programme asks.
        </EmptyState>
      </div>
    );
  }
  const required = plan.steps.filter((s) => !s.optional).length;
  const parallel = plan.tracks.length > 1;
  const extraCost = plan.unknownCostWithOptional.filter((c) => !plan.unknownCost.includes(c));
  const extraTime = plan.unknownDurationWithOptional.filter((c) => !plan.unknownDuration.includes(c));
  return (
    <div className="flex flex-col gap-6">
      <AutoGrid min={320}>
        <Totals id="required" title={`What you need now (${required} ${required === 1 ? 'step' : 'steps'})`} totals={plan.totals}
          steps={required} noCost={plan.unknownCost.length} noTime={plan.unknownDuration.length} />
        {plan.steps.some((s) => s.optional) && (
          <Totals id="with-optional" title="Including what only a contract might ask for" totals={plan.totalsWithOptional}
            steps={plan.steps.length} noCost={plan.unknownCostWithOptional.length} noTime={plan.unknownDurationWithOptional.length} />
        )}
      </AutoGrid>
      <Callout title="Read the ranges with care">
        <p className="m-0">{plan.label.charAt(0).toUpperCase() + plan.label.slice(1)}: the figures come from vendors and public notes, and no neutral body publishes prices. Money is shown in the currency of the source and is never converted.</p>
        {plan.unknownCost.length > 0 && <p className="m-0">No cost is stated in the sources for: {plan.unknownCost.map((c) => byCode.get(c)?.name ?? c).join('; ')}. It is not counted in the totals.</p>}
        {plan.unknownDuration.length > 0 && <p className="m-0">No time is stated in the sources for: {plan.unknownDuration.map((c) => byCode.get(c)?.name ?? c).join('; ')}. It is not counted in the totals.</p>}
        {extraCost.length > 0 && <p className="m-0">The total that includes what only a contract might ask for has no cost for: {extraCost.map((c) => byCode.get(c)?.name ?? c).join('; ')}. The sources give none, so it is not counted and the total is not complete.</p>}
        {extraTime.length > 0 && <p className="m-0">Nor a time for: {extraTime.map((c) => byCode.get(c)?.name ?? c).join('; ')}.</p>}
        {plan.notAdded.map((n) => <p key={n.code} className="m-0">Not added to any total: {n.text}</p>)}
        {parallel && <p className="m-0">Steps in different tracks do not depend on each other, so the total time is that of the slowest track, not their sum.</p>}
      </Callout>
      <div className={parallel ? 'grid items-start gap-6 lg:grid-cols-2' : 'flex flex-col gap-6'}>
        {plan.tracks.map((track, i) => (
          <section key={track.join('+')} aria-label={`Track ${i + 1}`} className="flex flex-col gap-3">
            <h2 className={parallel ? 'm-0 text-h4' : 'sr-only'}>Track {i + 1}{track.length === 1 ? '' : ` (${track.length} steps, in this order)`}</h2>
            <ol className="m-0 flex list-none flex-col gap-3 p-0">
              {track.map((code) => <StepCard key={code} s={byCode.get(code) as RoadmapStep} country={profile.country} onMark={onMark} />)}
            </ol>
          </section>
        ))}
      </div>
    </div>
  );
}

/** A step the visitor just marked, waiting for the re-scored plan to show it (the assessment is asked again after every change). */
interface Marked { code: string; name: string; status: 'held' | 'in_progress'; order: string[] }

export function RoadmapView() {
  const { profile, ready, update } = useProfile();
  const result = useAssessment(profile);
  const [marked, setMarked] = useState<Marked | null>(null);
  const [message, setMessage] = useState('');
  const plan = result.state === 'done' ? result.data.roadmap : null;

  // After "Mark as done" (WP-53): the card is gone once the plan is re-scored, so focus moves to the heading of the step that follows it (the one
  // before it if it was the last, the link back to the results if none is left) and the change is announced. "Mark as started" keeps the card:
  // focus goes to its "Mark as done" button, because the button that was pressed is gone.
  useEffect(() => {
    if (result.state === 'error') setMarked(null);       // the plan will not arrive: do not move focus later, on an unrelated update
    if (!marked || !plan) return;
    const now = plan.steps.find((s) => s.code === marked.code);
    if (marked.status === 'held' ? now : now?.status !== 'in_progress') return;
    const left = plan.steps.map((s) => s.code);
    let target: Element | null;
    if (marked.status === 'held') {
      const at = marked.order.indexOf(marked.code);
      const next = marked.order.slice(at + 1).find((c) => left.includes(c)) ?? marked.order.slice(0, at).reverse().find((c) => left.includes(c));
      target = next ? document.querySelector(`[data-step-heading="${next}"]`) : document.querySelector('[data-roadmap-empty] a');
      setMessage(`${marked.name} is marked as done. ${left.length === 0 ? 'No step is left.' : left.length === 1 ? '1 step is left.' : `${left.length} steps are left.`} Your results are re-scored.`);
    } else {
      target = document.querySelector(`[data-mark-done="${marked.code}"]`);
      setMessage(`${marked.name} is marked as started. Your results are re-scored.`);
    }
    if (target instanceof HTMLElement) target.focus();
    setMarked(null);
  }, [marked, plan, result.state]);

  if (!ready || profile === null) return <Skeleton className="h-56" />;
  if (!profile.country) return <NoProfile />;
  const mark = (code: string, status: 'held' | 'in_progress') => {
    setMessage('');
    setMarked({ code, name: plan?.steps.find((s) => s.code === code)?.name ?? code, status, order: plan?.steps.map((s) => s.code) ?? [] });
    update((p) => withStatus(p, code, status));
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-transparent bg-surface p-5">
        <p className="m-0 text-body">Steps in order, for a company established in <strong>{countryName(profile.country)}</strong>. Marking a step re-scores your results.</p>
        <Button href="/readiness/results" variant="secondary">My results</Button>
        {/* Always in the page, so that a screen reader announces the text when it is set. */}
        <p role="status" aria-live="polite" className={message ? 'm-0 w-full text-small font-semibold' : 'sr-only'}>{message}</p>
      </div>
      <AnswerProblems problems={answerProblems(profile)} />
      {(result.state === 'loading' || result.state === 'idle') && <div role="status" aria-label="Computing your roadmap"><Skeleton className="h-56" /></div>}
      {result.state === 'error' && <ErrorState title="The roadmap could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && <RoadmapBody plan={result.data.roadmap} profile={profile} onMark={mark} />}
    </div>
  );
}
