'use client';

import Link from 'next/link';
import { ArrowRight, ChevronDown, Pencil, Printer } from 'lucide-react';
import { Icon } from '@/components/dg/icon';
import { COUNTRIES, countryName } from '@/lib/taxonomy';
import { isoDay } from '@/lib/readiness';
import { SUPPLY_ROUTES, answerProblems, hasSupplier, skippedFields, wantsEuFunding, type Profile } from '@/lib/profile';
import { Callout } from '@/components/dg/blocks';
import { Button } from '@/components/dg/button';
import { EmptyState, ErrorState, Skeleton } from '@/components/dg/feedback';
import { AutoGrid } from '@/components/dg/auto-grid';
import type { Assessment } from '@/lib/readiness-types';
import { ConsultantNote, ProgrammeCard } from './rules';
import { useAssessment, useDemand, useProfile } from './use-readiness';
import { DemandSummary } from './demand';
import { ApproachSummary, OpenNowBlock } from './approach';

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
function Programmes({ assessments, supplier, euFunding, skipped = [], profile }: { assessments: Assessment['assessments']; supplier: boolean; euFunding: boolean; skipped?: string[]; profile: Profile }) {
  // the national route first (the Spanish Ministry of Defence), then NATO and NSPA (SUPPLY_ROUTES), then any other route
  const rank = (code: string) => { const i = (SUPPLY_ROUTES as readonly string[]).indexOf(code); return i < 0 ? 99 : i; };
  const routes = assessments.filter((a) => a.kind === 'route').sort((x, y) => rank(x.programme) - rank(y.programme));
  const funding = assessments.filter((a) => a.kind !== 'route');
  const card = (a: Assessment['assessments'][number]) => <ProgrammeCard key={a.programme} a={a} supplier={supplier} skipped={skipped} profile={profile} />;
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

/**
 * WP-99 (p05): the programmes above are the ones with rules encoded (EDF, EDIP, its Ukraine Support Instrument, SAFE, the supply routes).
 * The other funding a company targets, Digital Europe (the ECCC cyber calls), the EIC and the national programmes, has no programme rules
 * here: each call's own rules are read from its document and compared with these answers on the funding list. So these cards say that and
 * lead to the calls, with "Fits my profile" on over the whole list (`fit=1`).
 */
export function fundingLinks(country: string): { key: string; title: string; text: string; href: string }[] {
  const own = country in COUNTRIES && country !== 'EU' ? country : null;
  return [
    { key: 'DIGITAL', title: 'Digital Europe (the ECCC cybersecurity calls among them)', href: '/funding?programme=DIGITAL&fit=1#results',
      text: 'No programme rules are encoded here. Each call’s own rules (who may apply, the eligible countries, designated bodies such as National Coordination Centres or National Cyber Hubs) are read from its call document and compared with your answers.' },
    { key: 'EIC', title: 'EIC (Horizon Europe): Accelerator, Pathfinder, STEP', href: '/funding?programme=HORIZON&q=EIC&fit=1#results',
      text: 'The rules of the EIC work programme that we read (the Accelerator is for SMEs; STEP needs an investor’s pre-commitment of at least 20 % of the round) are compared with your size, group and investor answers.' },
    { key: 'NATIONAL', title: own ? `National calls of ${countryName(own)}` : 'National funding calls', href: `/funding?programme=NATIONAL${own ? `&country=${own}` : ''}&fit=1#results`,
      text: 'Calls of national agencies (France’s AID, Poland’s NCBR, Sweden’s Vinnova, Spain’s BDNS and others): their rules are read from the agency’s page where we hold it, and the call says when they are not.' },
  ];
}

/**
 * WP-107 (p09): Horizon Europe Cluster 3 (civil security) is about half of the open and forthcoming calls, and the results had no card for it.
 * No programme verdict is computed (its rules differ by topic); the card states the regulation's general rules and leads to the CL3 calls,
 * each judged on its own call text with "Fits my profile".
 */
export const HORIZON_CL3_HREF = '/funding?programme=HORIZON&q=CL3&fit=1#results';
function HorizonCl3() {
  return (
    <section aria-labelledby="horizon-cl3" className="flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5 sm:p-7" data-horizon-cl3>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="horizon-cl3" className="m-0 text-h3">Horizon Europe, Cluster 3: civil security for society</h2>
        <Button href={HORIZON_CL3_HREF} variant="secondary" iconRight={ArrowRight}>Cluster 3 calls that fit your profile</Button>
      </div>
      <p className="m-0 max-w-prose text-body text-ink-muted">
        No programme verdict is given here: the rules of a Cluster 3 call are set topic by topic in the work programme, and each call is judged on
        its own text against your answers on the funding list.
      </p>
      <ul className="m-0 flex max-w-prose list-disc flex-col gap-1 pl-5 text-small">
        <li>A collaborative action needs at least three independent legal entities, each established in a different EU Member State or associated country, at least one of them in a Member State (Regulation (EU) 2021/695, Article 22(2)).</li>
        <li>For security-related topics the work programme may limit participation to entities established in Member States, or also in named associated or other countries, and exclude entities controlled from non-eligible countries (Article 22(5)). Your answer on control from outside the EU matters there.</li>
        <li>Some topics are security-sensitive and may involve classified information: the call text says so, and those proposals go through a security scrutiny.</li>
      </ul>
      <p className="m-0 text-small text-ink-muted">
        Source: <a href="http://data.europa.eu/eli/reg/2021/695/oj" target="_blank" rel="noopener noreferrer" className="font-semibold">Regulation (EU) 2021/695 (Horizon Europe), Article 22</a>.
      </p>
    </section>
  );
}

function OtherFunding({ country }: { country: string }) {
  return (
    <section aria-labelledby="other-funding" className="flex flex-col gap-3" data-other-funding>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="other-funding" className="m-0 text-h2">Digital Europe, the EIC and national calls</h2>
        <Button href="/funding?fit=1#results" iconRight={ArrowRight}>See matching calls</Button>
      </div>
      <p className="m-0 max-w-prose text-body text-ink-muted">
        These have no programme verdict above: the funding list judges each call on its own rules against your answers. “See matching calls”
        opens every open call with “Fits my profile” on.
      </p>
      <ul className="m-0 grid list-none gap-3 p-0 md:grid-cols-3">
        {fundingLinks(country).map((f) => (
          <li key={f.key} className="flex flex-col gap-2 rounded-lg border border-edge bg-surface p-4" data-other-funding-card={f.key}>
            <h3 className="m-0 text-body font-bold">{f.title}</h3>
            <p className="m-0 text-small">{f.text}</p>
            <Link href={f.href} className="mt-auto inline-flex min-h-11 items-center gap-1 font-semibold">Calls that fit your profile<Icon icon={ArrowRight} size="inline" /></Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** `fromSupplier` (WP-97): reached from the supplier profile (`?from=supplier`): "Change my answers" leads back there. */
export function ResultsView({ fromSupplier = false }: { fromSupplier?: boolean } = {}) {
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
          {fromSupplier
            ? <Button href="/readiness/supplier" variant="secondary" icon={Pencil}>Change my answers</Button>
            : (
              <>
                <Button href="/readiness" variant="secondary" icon={Pencil}>Change my answers</Button>
                {/* WP-73: the questions of the supply routes are asked there, so the link is shown before the page was used too */}
                <Button href="/readiness/supplier" variant="secondary" icon={Pencil}>{hasSupplier(profile) ? 'Change my supplier profile' : 'Answer the supplier questions'}</Button>
              </>
            )}
          {hasSupplier(profile) && <Button href="/readiness/supplier/report" variant="secondary" icon={Printer}>My supplier report</Button>}
          <Button href="/readiness/roadmap" iconRight={ArrowRight}>See my roadmap</Button>
        </div>
      </div>

      <AnswerProblems problems={answerProblems(profile)} />
      {/* WP-97: what is open now in the company's own country under its codes comes first */}
      <OpenNowBlock result={demand} country={profile.country} />
      <ApproachSummary result={demand} country={profile.country} cpv={profile.supplier.cpv} />
      <DemandSummary result={demand} country={profile.country} />
      {(result.state === 'loading' || result.state === 'idle') && <Loading />}
      {result.state === 'error' && <ErrorState title="The check could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && (
        <>
          <Programmes assessments={result.data.assessments} supplier={hasSupplier(profile)} euFunding={wantsEuFunding(profile)} skipped={skippedFields(profile)} profile={profile} />
          {(!hasSupplier(profile) || wantsEuFunding(profile)) && <HorizonCl3 />}
          {(!hasSupplier(profile) || wantsEuFunding(profile)) && <OtherFunding country={profile.country} />}
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
              <ProgrammeCard a={a} general supplier={hasSupplier(profile)} profile={profile} />
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
