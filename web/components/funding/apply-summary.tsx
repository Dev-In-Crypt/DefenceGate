'use client';

import { useEffect, useState } from 'react';
import { CircleAlert, CircleCheck, CircleX } from 'lucide-react';
import { applySummary, SUMMARY_WORD } from '@/lib/funding-path';
import type { Call } from '@/lib/types';
import { Select } from '@/components/dg/form';
import { Icon } from '@/components/dg/icon';
import { COUNTRY_OPTIONS } from '@/components/readiness/wizard';
import { useProfile } from '@/components/readiness/use-readiness';

const ICON = { yes: CircleCheck, check: CircleAlert, no: CircleX } as const;

/**
 * "Can I apply?" on the first screen of a call (WP-91, UX audit 6): two or three lines for one country, from the rules the API
 * evaluated for that country's group and from the call document's facts. The country is the saved profile's until the visitor
 * picks another here; nothing is sent or stored from this box.
 */
export function ApplySummary({ call }: { call: Pick<Call, 'rulesApply' | 'documentEligibility'> }) {
  const { profile, ready } = useProfile();
  const [country, setCountry] = useState('');
  const [picked, setPicked] = useState(false);
  useEffect(() => {
    if (ready && profile?.country && !picked) setCountry(profile.country);
  }, [ready, profile?.country, picked]);
  const summary = applySummary(call, country, profile?.applicantKind ?? '');
  return (
    <section aria-labelledby="apply-summary" data-apply-summary className="flex max-w-prose flex-col gap-2 rounded-lg border border-line bg-surface p-4">
      <h2 id="apply-summary" className="m-0 text-h4">Can I apply?</h2>
      <Select label="Your country" placeholder="Choose your country" options={COUNTRY_OPTIONS} value={country} className="sm:max-w-xs"
        onChange={(e) => { setPicked(true); setCountry(e.target.value); }} />
      <div aria-live="polite" className="flex flex-col gap-1">
        {summary ? (
          <>
            <p className="m-0 flex items-center gap-2 text-body font-bold" data-verdict={summary.verdict}>
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
