'use client';

import Link from 'next/link';
import { ArrowRight, ChevronDown, Pencil, Printer } from 'lucide-react';
import { Icon } from '@/components/dg/icon';
import { countryName } from '@/lib/taxonomy';
import { isoDay } from '@/lib/readiness';
import { SUPPLY_ROUTES, answerProblems, hasSupplier, skippedFields, wantsEuFunding } from '@/lib/profile';
import { Callout } from '@/components/dg/blocks';
import { Button } from '@/components/dg/button';
import { EmptyState, ErrorState, Skeleton } from '@/components/dg/feedback';
import { AutoGrid } from '@/components/dg/auto-grid';
import type { Assessment } from '@/lib/readiness-types';
import { ConsultantNote, ProgrammeCard } from './rules';
import { useAssessment, useDemand, useProfile } from './use-readiness';
import { DemandSummary } from './demand';
import { ApproachSummary } from './approach';

/** Shown while the profile is read from the browser and while the verdict is computed. */
function Loading() {
  return (
    <div role="status" aria-label="Computing your results" className="flex flex-col gap-4">
      <Skeleton className="h-6 w-64" />
      <AutoGrid fill min={400}>{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-56" />)}</AutoGrid>
    </div>
  );
}

export function NoProfile() {
  return (
    <EmptyState title="No answers in this browser yet" action={<Button href="/readiness" iconRight={ArrowRight}>Answer the questions</Button>}>
      The check needs a few answers about your company. They are kept in this browser only.
    </EmptyState>
  );
}

/**
 * An answer that is in the profile and cannot be used (a share of 150 %, a country left unchosen) is treated as not given. The pages that
 * show a result say so here and say why, instead of only counting a missing answer (WP-53, T6).
 */
export function AnswerProblems({ problems }: { problems: { step: number; text: string }[] }) {
  if (problems.length === 0) return null;
  return (
    <Callout title={problems.length === 1 ? 'One of your answers is not used' : `${problems.length} of your answers are not used`}>
      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {problems.map((p) => (
          <li key={p.text}>{p.text}{' '}<Link href={`/readiness?step=${p.step}`} className="inline-flex min-h-11 items-center font-semibold">Change it</Link></li>
        ))}
      </ul>
    </Callout>
  );
}

/**
 * WP-89 (UX audit, section 4): a supplier's results lead with its supply routes (the Spanish Ministry of Defence, NATO and NSPA); the EU
 * funding programmes follow, collapsed under "If you also want EU funding" unless it said it wants it. Someone who came for EU funding (the
 * readiness check) sees the programmes first, as before.
 */
function Programmes({ assessments, supplier, euFunding, skipped = [] }: { assessments: Assessment['assessments']; supplier: boolean; euFunding: boolean; skipped?: string[] }) {
  // the national route first (the Spanish Ministry of Defence), then NATO and NSPA (SUPPLY_ROUTES), then any other route
  const rank = (code: string) => { const i = (SUPPLY_ROUTES as readonly string[]).indexOf(code); return i < 0 ? 99 : i; };
  const routes = assessments.filter((a) => a.kind === 'route').sort((x, y) => rank(x.programme) - rank(y.programme));
  const funding = assessments.filter((a) => a.kind !== 'route');
  const card = (a: Assessment['assessments'][number]) => <ProgrammeCard key={a.programme} a={a} supplier={supplier} skipped={skipped} />;
  if (!supplier) {
    return (
      <section aria-labelledby="programmes" className="flex flex-col gap-4">
        <h2 id="programmes" className="m-0 text-h2">Where you stand, programme by programme</h2>
        <AutoGrid fill min={400}>{assessments.map(card)}</AutoGrid>
      </section>
    );
  }
  return (
    <section aria-labelledby="programmes" className="flex flex-col gap-4" data-supplier-routes>
      <h2 id="programmes" className="m-0 text-h2">Where you stand, programme by programme</h2>
      <AutoGrid fill min={400}>{routes.map(card)}</AutoGrid>
      {funding.length > 0 && (euFunding ? (
        <div className="flex flex-col gap-3" data-eu-funding="open">
          <h3 className="m-0 text-h3">EU funding programmes</h3>
          <AutoGrid fill min={400}>{funding.map(card)}</AutoGrid>
        </div>
      ) : (
        <details className="group flex flex-col gap-3" data-eu-funding="collapsed">
          <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-2 text-h4 font-bold [&::-webkit-details-marker]:hidden">
            If you also want EU funding ({funding.length} programmes)
            <Icon icon={ChevronDown} size="inline" className="transition-transform duration-dg group-open:rotate-180" />
          </summary>
          <p className="m-0 max-w-prose text-small text-ink-muted">
            EU grants and loans (EDF, EDIP, SAFE) are a separate path from supplying a ministry or a prime. Your roadmap leaves out what only they
            ask, such as the PIC, until you say on your supplier profile that you want EU funding.
          </p>
          <AutoGrid fill min={400}>{funding.map(card)}</AutoGrid>
        </details>
      ))}
    </section>
  );
}

export function ResultsView() {
  const { profile, ready } = useProfile();
  const result = useAssessment(profile);
  // WP-80: one demand request for both sections that read it ("who to approach" first, then who buys); none without the supplier page
  const demand = useDemand(profile && hasSupplier(profile) ? profile : null);
  if (!ready || profile === null) return <Loading />;
  if (!profile.country) return <NoProfile />;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-transparent bg-surface p-5">
        <p className="m-0 text-body">
          {profile.name ? <strong>{profile.name}</strong> : 'Your company'}, established in <strong>{countryName(profile.country)}</strong>
          {profile.country === 'XX' && ' (a country that is not listed)'}.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button href="/readiness" variant="secondary" icon={Pencil}>Change my answers</Button>
          {/* WP-73: the questions of the supply routes are asked there, so the link is shown before the page was used too */}
          <Button href="/readiness/supplier" variant="secondary" icon={Pencil}>{hasSupplier(profile) ? 'Change my supplier profile' : 'Answer the supplier questions'}</Button>
          {hasSupplier(profile) && <Button href="/readiness/supplier/report" variant="secondary" icon={Printer}>My supplier report</Button>}
          <Button href="/readiness/roadmap" iconRight={ArrowRight}>See my roadmap</Button>
        </div>
      </div>

      <AnswerProblems problems={answerProblems(profile)} />
      <ApproachSummary result={demand} country={profile.country} cpv={profile.supplier.cpv} />
      <DemandSummary result={demand} />
      {(result.state === 'loading' || result.state === 'idle') && <Loading />}
      {result.state === 'error' && <ErrorState title="The check could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && (
        <>
          <Programmes assessments={result.data.assessments} supplier={hasSupplier(profile)} euFunding={wantsEuFunding(profile)} skipped={skippedFields(profile)} />
          {(result.data.consultants ?? []).length > 0 && (
            <section aria-labelledby="consultants" className="flex flex-col gap-3">
              <h2 id="consultants" className="m-0 text-h2">Where you need a specialist</h2>
              <p className="m-0 max-w-prose text-body text-ink-muted">These questions are settled by a classification, a legal reading or the prime contractor, not by this check. Each says whom to ask.</p>
              <ul className="m-0 flex list-none flex-col gap-3 p-0">
                {(result.data.consultants ?? []).map((f) => (
                  <li key={f.key} className="flex flex-col gap-1 rounded-lg border border-edge bg-surface p-4" data-consultant-flag={f.key}>
                    <h3 className="m-0 text-body font-bold">{f.title}</h3>
                    <ConsultantNote text={f.text} />
                    {f.asks.map((a) => <p key={a.field} className="m-0 text-small text-ink-muted">To answer: {a.question}</p>)}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {result.data.general.map((a) => (
            <section key={a.programme} aria-labelledby="general" className="flex flex-col gap-4">
              <h2 id="general" className="m-0 text-h2">Other requirements that may apply to you</h2>
              {/* the card below carries the summary itself (QA n-5: the same paragraph was printed twice) */}
              <p className="m-0 max-w-prose text-body text-ink-muted">These rules do not change the verdicts above; they are listed in your roadmap when they apply to you.</p>
              <ProgrammeCard a={a} general supplier={hasSupplier(profile)} />
            </section>
          ))}
          <p className="m-0 max-w-prose text-small text-ink-muted">
            {result.data.notice} Rules last reviewed on {isoDay(result.data.rulesReviewed)}. How we read the sources:{' '}
            <Link href="/requirements" className="font-semibold">the requirements catalogue</Link>.
          </p>
        </>
      )}
    </div>
  );
}
