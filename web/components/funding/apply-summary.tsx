'use client';

import { useEffect, useState } from 'react';
import { CircleAlert, CircleCheck, CircleHelp, CircleX } from 'lucide-react';
import { applySummary, SUMMARY_WORD } from '@/lib/funding-path';
import { fitLabel, shownFit } from '@/lib/fit';
import { useFit } from '@/lib/fit-hooks';
import { fitFor, isLoaded } from '@/lib/fit-store';
import type { Call } from '@/lib/types';
import { Select } from '@/components/dg/form';
import { Icon } from '@/components/dg/icon';
import { COUNTRY_OPTIONS } from '@/components/readiness/wizard';
import { useProfile } from '@/components/readiness/use-readiness';

const ICON = { yes: CircleCheck, check: CircleAlert, no: CircleX, unknown: CircleHelp } as const;

/**
 * WP-93 (finding 5): with a saved profile, the first screen says the one verdict the list badge says (lib/fit.ts `callFit`, through the
 * same store), with what blocks or what is left to check. The country box below it still shows any other country, for that country alone.
 */
function ProfileVerdict({ id }: { id: string }) {
  const s = useFit(id);
  if (!s.ready || !s.hasProfile) return null;
  if (!isLoaded(id)) return <p role="status" className="m-0 text-body text-ink-muted">Comparing the call with your saved profile…</p>;
  const r = fitFor(id);
  const shown = shownFit(r);
  const lines = (r.result?.lines ?? []).filter((l) => l.verdict !== 'yes');
  return (
    <div className="flex flex-col gap-1" data-profile-verdict={shown}>
      <p className="m-0 flex items-center gap-2 text-body font-bold">
        <Icon icon={ICON[shown]} size="button" /><span><span className="sr-only">Your saved profile: </span>{fitLabel(r).word}</span>
      </p>
      {shown === 'unknown' ? (
        <p className="m-0 text-body">Rules not read: check the call document. Nothing we hold says who may apply to this call.</p>
      ) : (
        <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-body">
          {r.blockedBy.filter((b) => !lines.some((l) => l.label === b)).map((b) => <li key={b} data-profile-line="programme">{b}.</li>)}
          {lines.map((l) => <li key={l.key} data-profile-line={l.key}><strong>{l.label}:</strong> {l.reason}</li>)}
          {r.conditions.filter((c) => !r.blockedBy.includes(c)).map((c) => <li key={c} data-profile-line="condition">{c}</li>)}
        </ul>
      )}
      <p className="m-0 text-small text-ink-muted">For the profile saved in this browser; the same verdict as the list of calls. The details are further down the page.</p>
    </div>
  );
}

/**
 * "Can I apply?" on the first screen of a call (WP-91, UX audit 6): two or three lines for one country, from the rules the API
 * evaluated for that country's group and from the call document's facts. The country is the saved profile's until the visitor
 * picks another here; nothing is sent or stored from this box. WP-93: with a saved profile and its own country, the one verdict.
 */
export function ApplySummary({ call }: { call: Pick<Call, 'id' | 'programme' | 'topicId' | 'rulesApply' | 'documentEligibility'> }) {
  const { profile, ready } = useProfile();
  const [country, setCountry] = useState('');
  const [picked, setPicked] = useState(false);
  useEffect(() => {
    if (ready && profile?.country && !picked) setCountry(profile.country);
  }, [ready, profile?.country, picked]);
  const own = ready && Boolean(profile?.country) && country === profile?.country;
  const summary = applySummary(call, country, profile?.applicantKind ?? '');
  return (
    <section aria-labelledby="apply-summary" data-apply-summary className="flex max-w-prose flex-col gap-2 rounded-lg border border-line bg-surface p-4">
      <h2 id="apply-summary" className="m-0 text-h4">Can I apply?</h2>
      <Select label="Your country" placeholder="Choose your country" options={COUNTRY_OPTIONS} value={country} className="sm:max-w-xs"
        onChange={(e) => { setPicked(true); setCountry(e.target.value); }} />
      <div aria-live="polite" className="flex flex-col gap-1">
        {own && <ProfileVerdict id={call.id} />}
        {summary ? (
          <>
            {own && <p className="m-0 mt-2 text-small font-semibold text-ink-muted">On the country alone, for any company from it:</p>}
            <p className={own ? 'm-0 flex items-center gap-2 text-small font-semibold' : 'm-0 flex items-center gap-2 text-body font-bold'} data-verdict={summary.verdict}>
              <Icon icon={ICON[summary.verdict]} size="button" />{SUMMARY_WORD[summary.verdict]}
            </p>
            <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-body">
              {summary.lines.map((l) => <li key={l.key} data-line={l.key}>{l.text}</li>)}
            </ul>
          </>
        ) : (
          <p className="m-0 text-body text-ink-muted">Choose your country to see whether a company from it can apply.</p>
        )}
      </div>
      <p className="m-0 text-small text-ink-muted">
        From the programme’s rules and the call document as we hold them; indicative, not legal advice. Nothing is sent from this box. The rules and their sources are further down the page.
      </p>
    </section>
  );
}

/** Children shown to a visitor whose saved profile is established in Ukraine only (the note on the non-government-controlled areas). */
export function UkraineOnly({ children }: { children: React.ReactNode }) {
  const { profile, ready } = useProfile();
  return ready && profile?.country === 'UA' ? <>{children}</> : null;
}
