'use client';

import { useSyncExternalStore } from 'react';
import { CircleAlert, CircleCheck, CircleHelp, CircleX } from 'lucide-react';
import { applySummary } from '@/lib/funding-path';
import { answersFit, answersOf, asksUaPartner, fitLabel, shownFit, type Answers, type FitResult } from '@/lib/fit';
import type { EligibilityFacts } from '@/lib/eligibility-check';
import { useFit } from '@/lib/fit-hooks';
import { fitFor, isLoaded, lookupFailed } from '@/lib/fit-store';
import type { Call } from '@/lib/types';
import { Select } from '@/components/dg/form';
import { Icon } from '@/components/dg/icon';
import { COUNTRY_OPTIONS } from '@/components/readiness/wizard';
import { useProfile } from '@/components/readiness/use-readiness';

const ICON = { yes: CircleCheck, check: CircleAlert, no: CircleX, unknown: CircleHelp } as const;

export const ORG_TYPES = [
  { value: 'sme', label: 'Small or medium enterprise' }, { value: 'large', label: 'Large company' },
  { value: 'public', label: 'Public body' }, { value: 'university', label: 'University or research organisation' },
  { value: 'individual', label: 'Individual (natural person)' },
];

// ---------------------------------------------------------------- WP-109: the one case of a call page

/**
 * The answers given on a call page, shared by its first screen ("Can I apply?") and its form ("Check your company"): one case, one
 * verdict (p09, 24 Oct: the two computed their own). Absent: the visitor changed nothing, and with a saved profile both show its verdict.
 * Kept in this page only; nothing is sent or stored.
 */
const cases = new Map<string, Answers>();
const listeners = new Set<() => void>();
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };
const EMPTY: Answers = { country: '', orgType: '', hasPartners: '', controlledAbroad: '' };

export interface PageCase {
  /** The answers shown: the visitor's case, else the saved profile's, else none. */
  answers: Answers;
  /** The visitor has changed nothing and a saved profile with a country is held: its verdict (`callFit`) is the page's. */
  profileMode: boolean;
  /** Change answers: the case starts from what is shown, and what only the saved profile knows no longer applies to it. */
  set: (patch: Partial<Answers>) => void;
}

export function usePageCase(callId: string): PageCase {
  const edited = useSyncExternalStore(subscribe, () => cases.get(callId), () => undefined);
  const { profile, ready } = useProfile();
  const held = ready && profile ? answersOf(profile) : null;
  const answers = edited ?? held ?? EMPTY;
  return {
    answers,
    profileMode: !edited && held !== null,
    set: (patch) => {
      cases.set(callId, { ...answers, ...patch });
      for (const l of listeners) l();
    },
  };
}

/** The one verdict of the page in its current state: the saved profile's while nothing is changed, else the answers'. */
export function pageFit(call: { programme: string; topicId: string } & Pick<Call, 'rulesApply' | 'documentEligibility'>, c: PageCase, own: FitResult | null): FitResult {
  if (c.profileMode && own) return own;
  return answersFit({ facts: call.documentEligibility?.facts as EligibilityFacts | undefined, programme: call.programme, topic: call.topicId, rulesApply: call.rulesApply }, c.answers);
}

/**
 * WP-93 (finding 5): with a saved profile, the first screen says the one verdict the list badge says (lib/fit.ts `callFit`, through the
 * same store), with what blocks or what is left to check.
 */
function ProfileVerdict({ id }: { id: string }) {
  const s = useFit(id);
  if (!s.ready || !s.hasProfile) return null;
  if (!isLoaded(id)) return <p role="status" className="m-0 text-body text-ink-muted">Comparing the call with your saved profile…</p>;
  if (lookupFailed(id)) {
    // WP-102 (BM-01 69): a failed look-up is not "rules not read"; the rules read are further down the page
    return <p role="status" className="m-0 text-body text-ink-muted" data-profile-verdict="failed">Your saved profile could not be compared with this call just now. Reload the page; the rules read from the call are further down.</p>;
  }
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
      <p className="m-0 text-small text-ink-muted">For the profile saved in this browser; the same verdict as the list of calls and the form further down.</p>
    </div>
  );
}

/**
 * "Can I apply?" on the first screen of a call (WP-91, UX audit 6). WP-109: one verdict for the page. With a saved profile and nothing
 * changed, its verdict; otherwise the verdict of the answers given here and in the form further down (the same case), with the
 * questions this box needs: the country and the kind of organisation. The lines say what the programme's rules and the call document
 * say for that country.
 */
export function ApplySummary({ call }: { call: Pick<Call, 'id' | 'programme' | 'topicId' | 'rulesApply' | 'documentEligibility'> }) {
  const c = usePageCase(call.id);
  const { answers } = c;
  const summary = applySummary(call, answers.country, answers.orgType === 'public' ? 'contracting_authority' : answers.orgType ? 'company_or_research' : '');
  const r = c.profileMode ? null : pageFit(call, c, null);
  const shown = r ? shownFit(r) : 'unknown';
  const blocking = (r?.result?.lines ?? []).filter((l) => l.verdict === 'no' && l.key !== 'who' && !l.key.startsWith('rule-'));
  return (
    <section aria-labelledby="apply-summary" data-apply-summary className="flex max-w-prose flex-col gap-2 rounded-lg border border-line bg-surface p-4">
      <h2 id="apply-summary" className="m-0 text-h4">Can I apply?</h2>
      <div className="grid gap-3 sm:grid-cols-2 print:hidden">
        <Select label="Your country" placeholder="Choose your country" options={COUNTRY_OPTIONS} value={answers.country}
          onChange={(e) => c.set({ country: e.target.value })} />
        <Select label="Your kind of organisation" placeholder="Choose" options={ORG_TYPES} value={answers.orgType}
          onChange={(e) => c.set({ orgType: e.target.value as Answers['orgType'] })} />
        {asksUaPartner(call, answers.country) && (
          <Select label="Does a legal entity established in Ukraine take part with you?" placeholder="Choose" className="sm:col-span-2"
            options={[{ value: 'yes', label: 'Yes, with its executive management in Ukraine' }, { value: 'no', label: 'No' }, { value: 'unsure', label: 'Not sure' }]}
            value={answers.uaPartner ?? ''} onChange={(e) => c.set({ uaPartner: e.target.value as Answers['uaPartner'] })} />
        )}
      </div>
      <div aria-live="polite" className="flex flex-col gap-1">
        {c.profileMode && <ProfileVerdict id={call.id} />}
        {!c.profileMode && r && answers.country && (
          <>
            <p className="m-0 flex items-center gap-2 text-body font-bold" data-verdict={shown} data-page-verdict>
              <Icon icon={ICON[shown]} size="button" />{fitLabel(r).word}
            </p>
            {blocking.length > 0 && (
              <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-body">
                {blocking.map((l) => <li key={l.key} data-line={`block-${l.key}`}><strong>{l.label}:</strong> {l.reason}</li>)}
              </ul>
            )}
          </>
        )}
        {summary && answers.country ? (
          <>
            {c.profileMode && <p className="m-0 mt-2 text-small font-semibold text-ink-muted" data-verdict={summary.verdict}>What the rules say for any organisation of this country:</p>}
            <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-body">
              {summary.lines.map((l) => <li key={l.key} data-line={l.key}>{l.text}</li>)}
            </ul>
          </>
        ) : (
          <p className="m-0 text-body text-ink-muted">Choose your country to see whether an organisation from it can apply.</p>
        )}
        {!c.profileMode && answers.country && (
          <p className="m-0 text-small text-ink-muted">For the answers given here and in “Check your company” further down, which asks what else this call needs to know.</p>
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
