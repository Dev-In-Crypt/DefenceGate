'use client';

import Link from 'next/link';
import { ArrowRight, Check, Play } from 'lucide-react';
import { countryName } from '@/lib/taxonomy';
import { withStatus, type Profile } from '@/lib/profile';
import { CATEGORY_WORD, daysRange, formatDays, formatRange, isoDay, joinWords, programmeName, requirementSlug } from '@/lib/readiness';
import type { Roadmap, RoadmapStep, RoadmapTotals } from '@/lib/readiness-types';
import { safeHttpUrl } from '@/lib/safe-url';
import { Button } from '@/components/dg/button';
import { Callout } from '@/components/dg/blocks';
import { EmptyState, ErrorState, Skeleton } from '@/components/dg/feedback';
import { NoProfile } from './results';
import { useAssessment, useProfile } from './use-readiness';

function Totals({ title, totals, id }: { title: string; totals: RoadmapTotals; id: string }) {
  const cost = totals.cost.length === 0
    ? (totals.freeSteps.length > 0 ? 'Free' : 'Nothing is stated')
    : totals.cost.map((c) => `${c.currency} ${c.min.toLocaleString('en-GB')} to ${c.max.toLocaleString('en-GB')}`).join(' and ');
  return (
    <div className="flex flex-col gap-1 rounded-md bg-surface-inset p-4" data-totals={id}>
      <h3 className="m-0 text-body font-bold">{title}</h3>
      <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-body">
        <dt className="text-ink-muted">Cost</dt><dd className="m-0 font-mono tabular-nums">{cost}</dd>
        <dt className="text-ink-muted">Time</dt>
        <dd className="m-0 font-mono tabular-nums">{daysRange(totals.days.min, totals.days.max)}</dd>
      </dl>
    </div>
  );
}

function StepCard({ s, country, onMark }: { s: RoadmapStep; country: string; onMark: (code: string, status: 'held' | 'in_progress') => void }) {
  const blocking = s.blockingFor.length > 0;
  return (
    <li className="flex flex-col gap-3 rounded-lg border border-edge bg-surface p-5" data-step={s.code}>
      <div className="flex flex-wrap items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-pill bg-primary font-mono text-mono-strong text-on-primary" aria-hidden="true">{s.order}</span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h3 className="m-0 text-h4"><span className="sr-only">Step {s.order}: </span>{s.name}</h3>
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
        <Button variant="secondary" icon={Check} onClick={() => onMark(s.code, 'held')} aria-label={`Mark as done: ${s.name}`}>Mark as done</Button>
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
      <EmptyState title="Nothing left to obtain" action={<Button href="/readiness/results" iconRight={ArrowRight}>Back to my results</Button>}>
        On your answers, no requirement is missing. Your results page still lists what each programme asks.
      </EmptyState>
    );
  }
  const required = plan.steps.filter((s) => !s.optional).length;
  const parallel = plan.tracks.length > 1;
  const extraCost = plan.unknownCostWithOptional.filter((c) => !plan.unknownCost.includes(c));
  const extraTime = plan.unknownDurationWithOptional.filter((c) => !plan.unknownDuration.includes(c));
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 md:grid-cols-2">
        <Totals id="required" title={`What you need now (${required} ${required === 1 ? 'step' : 'steps'})`} totals={plan.totals} />
        {plan.steps.some((s) => s.optional) && <Totals id="with-optional" title="Including what only a contract might ask for" totals={plan.totalsWithOptional} />}
      </div>
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

export function RoadmapView() {
  const { profile, ready, update } = useProfile();
  const result = useAssessment(profile);
  if (!ready || profile === null) return <Skeleton className="h-56" />;
  if (!profile.country) return <NoProfile />;
  const mark = (code: string, status: 'held' | 'in_progress') => update((p) => withStatus(p, code, status));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-edge bg-surface p-5">
        <p className="m-0 text-body">Steps in order, for a company established in <strong>{countryName(profile.country)}</strong>. Marking a step re-scores your results.</p>
        <Button href="/readiness/results" variant="secondary">My results</Button>
      </div>
      {(result.state === 'loading' || result.state === 'idle') && <div role="status" aria-label="Computing your roadmap"><Skeleton className="h-56" /></div>}
      {result.state === 'error' && <ErrorState title="The roadmap could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && <RoadmapBody plan={result.data.roadmap} profile={profile} onMark={mark} />}
    </div>
  );
}
