'use client';

import Link from 'next/link';
import { ArrowRight, Pencil } from 'lucide-react';
import { countryName } from '@/lib/taxonomy';
import { isoDay } from '@/lib/readiness';
import { Button } from '@/components/dg/button';
import { EmptyState, ErrorState, Skeleton } from '@/components/dg/feedback';
import { ProgrammeCard } from './rules';
import { useAssessment, useProfile } from './use-readiness';

/** Shown while the profile is read from the browser and while the verdict is computed. */
function Loading() {
  return (
    <div role="status" aria-label="Computing your results" className="flex flex-col gap-4">
      <Skeleton className="h-6 w-64" />
      <div className="grid gap-4 lg:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-56" />)}</div>
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

      {(result.state === 'loading' || result.state === 'idle') && <Loading />}
      {result.state === 'error' && <ErrorState title="The check could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && (
        <>
          <section aria-labelledby="programmes" className="flex flex-col gap-4">
            <h2 id="programmes" className="m-0 text-h2">Where you stand, programme by programme</h2>
            <div className="grid gap-4 lg:grid-cols-2">
              {result.data.assessments.map((a) => <ProgrammeCard key={a.programme} a={a} />)}
            </div>
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
