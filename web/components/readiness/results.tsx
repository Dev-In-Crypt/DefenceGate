'use client';

import Link from 'next/link';
import { ArrowRight, Pencil } from 'lucide-react';
import { countryName } from '@/lib/taxonomy';
import { isoDay } from '@/lib/readiness';
import { answerProblems } from '@/lib/profile';
import { Callout } from '@/components/dg/blocks';
import { Button } from '@/components/dg/button';
import { EmptyState, ErrorState, Skeleton } from '@/components/dg/feedback';
import { AutoGrid } from '@/components/dg/auto-grid';
import { ProgrammeCard } from './rules';
import { useAssessment, useProfile } from './use-readiness';

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

export function ResultsView() {
  const { profile, ready } = useProfile();
  const result = useAssessment(profile);
  if (!ready || profile === null) return <Loading />;
  if (!profile.country) return <NoProfile />;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-edge bg-surface p-5">
        <p className="m-0 text-body">
          {profile.name ? <strong>{profile.name}</strong> : 'Your company'}, established in <strong>{countryName(profile.country)}</strong>
          {profile.country === 'XX' && ' (a country that is not listed)'}.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button href="/readiness" variant="secondary" icon={Pencil}>Change my answers</Button>
          <Button href="/readiness/roadmap" iconRight={ArrowRight}>See my roadmap</Button>
        </div>
      </div>

      <AnswerProblems problems={answerProblems(profile)} />
      {(result.state === 'loading' || result.state === 'idle') && <Loading />}
      {result.state === 'error' && <ErrorState title="The check could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && (
        <>
          <section aria-labelledby="programmes" className="flex flex-col gap-4">
            <h2 id="programmes" className="m-0 text-h2">Where you stand, programme by programme</h2>
            <AutoGrid fill min={400}>
              {result.data.assessments.map((a) => <ProgrammeCard key={a.programme} a={a} />)}
            </AutoGrid>
          </section>
          {result.data.general.map((a) => (
            <section key={a.programme} aria-labelledby="general" className="flex flex-col gap-4">
              <h2 id="general" className="m-0 text-h2">Other requirements that may apply to you</h2>
              <p className="m-0 max-w-prose text-body text-ink-muted">{a.summary} They do not change the verdicts above; they are listed in your roadmap when they apply to you.</p>
              <ProgrammeCard a={a} general />
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
