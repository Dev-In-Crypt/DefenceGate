'use client';

import { createContext, useContext, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Pencil } from 'lucide-react';
import type { EligibilityFacts } from '@/lib/eligibility-check';
import { callSummary } from '@/lib/call-readiness';
import { FIT_WORD, fitOf, type Fit } from '@/lib/fit';
import { isFinished, toRequest } from '@/lib/profile';
import { VERDICT_WORD, assess, daysRange, formatRange } from '@/lib/readiness';
import type { Assessment, CallTiming, ProgrammeAssessment } from '@/lib/readiness-types';
import { formatDateUtc } from '@/lib/format';
import { Button } from '@/components/dg/button';
import { Skeleton } from '@/components/dg/feedback';
import { useProfile } from '@/components/readiness/use-readiness';

/**
 * The facts read from the call's document, given by the "Can you apply?" panel that already holds them, so that
 * the page sends them once. Null where the call has none (not read, or no document).
 */
export const FactsContext = createContext<EligibilityFacts | null>(null);

type State = { state: 'idle' } | { state: 'loading' } | { state: 'error'; message: string } | { state: 'done'; data: Assessment };

/** The assessment of the saved profile for this call. Only with a profile; one request, aborted when the page goes. */
function useCallAssessment(callId: string, enabled: boolean, key: string): State & { retry: () => void } {
  const [result, setResult] = useState<State>({ state: 'idle' });
  const [attempt, setAttempt] = useState(0);
  const seq = useRef(0);
  useEffect(() => {
    if (!enabled || !key) { setResult({ state: 'idle' }); return; }
    const controller = new AbortController();
    const mine = ++seq.current;
    setResult({ state: 'loading' });
    assess({ ...JSON.parse(key), call: Number(callId) }, controller.signal).then(
      (data) => { if (mine === seq.current) setResult({ state: 'done', data }); },
      (e: unknown) => {
        if (controller.signal.aborted || mine !== seq.current) return;
        setResult({ state: 'error', message: e instanceof Error ? e.message : 'The check could not be computed.' });
      },
    );
    return () => controller.abort();
  }, [callId, enabled, key, attempt]);
  return { ...result, retry: () => setAttempt((n) => n + 1) };
}

const ROW = 'flex flex-col gap-0.5 text-body';

function Timing({ t, a, data }: { t: CallTiming; a: ProgrammeAssessment | undefined; data: Assessment }) {
  const names = new Map(data.roadmap.steps.map((s) => [s.code, s]));
  const blocking = (a?.rules ?? []).filter((r) => a?.blocking.includes(r.rule));
  // The rules that belong to the kind of action of this call (who may apply to common procurement) are judged with the call, so they
  // are in `notFixable` and not in the assessment of the programme.
  const known = new Set(blocking.map((r) => r.rule));
  const ofThisCall = t.notFixable.filter((n) => !known.has(n.rule));
  const steps = t.steps.map((c) => names.get(c)).filter((s): s is NonNullable<typeof s> => Boolean(s));
  return (
    <li className="flex flex-col gap-2 rounded-md border border-line p-4">
      <p className="m-0 text-body font-semibold">{t.name}: {VERDICT_WORD[t.verdict]}</p>
      <p className="m-0 text-body">{t.text}</p>
      {t.deadline && t.daysLeft !== null && t.daysLeft >= 0 && (
        <p className="m-0 text-small text-ink-muted">Deadline <time dateTime={t.deadline}>{formatDateUtc(t.deadline)}</time> UTC, about {Math.round(t.daysLeft)} days left.</p>
      )}
      {(blocking.length > 0 || ofThisCall.length > 0) && (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {blocking.map((r) => <li key={r.rule} className={ROW}><span><strong>{r.title}.</strong> {r.reason}</span></li>)}
          {ofThisCall.map((n) => <li key={n.rule} className={ROW}><span><strong>{n.title}.</strong> {n.reason}</span></li>)}
        </ul>
      )}
      {steps.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="m-0 text-small font-semibold">What you would need first</p>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {steps.map((s) => (
              <li key={s.code} className="text-body">
                <Link href={`/requirements/${s.code.replace(/^REQ-/, '').toLowerCase()}`} className="font-semibold">{s.name}</Link>
                {': '}{formatRange(s.cost)}, {s.days && s.days.min !== null && s.days.max !== null ? daysRange(s.days.min, s.days.max) : 'time not stated'}
                {s.cost?.label ? ` (${s.cost.label})` : ''}
              </li>
            ))}
          </ul>
          <p className="m-0 text-small text-ink-muted">
            Together {t.fastestPathDays.min} to {t.fastestPathDays.max} days. <Link href="/readiness/roadmap" className="font-semibold">Your roadmap</Link> has the order, the issuers and the parallel tracks.
          </p>
        </div>
      )}
    </li>
  );
}

function Loading() {
  return <div role="status" aria-label="Computing your readiness for this call" className="flex flex-col gap-3"><Skeleton className="h-6 w-64" /><Skeleton className="h-24" /></div>;
}

/**
 * "Your readiness for this call" (WP-32). Without a saved profile: the way to the five-step check, and nothing else
 * (no request, no work). With one: the rules read from the call's document against the profile, and the programme's
 * rules with the time left, from `POST /v1/readiness/assess` with the call's id. The profile never leaves the browser
 * except as that request, which stores nothing.
 */
export function CallReadiness({ callId, headingLevel = 'h3' }: { callId: string; headingLevel?: 'h2' | 'h3' }) {
  const H = headingLevel;
  const facts = useContext(FactsContext);
  const { profile, ready } = useProfile();
  const usable = ready && profile !== null && profile.country !== '';
  const request = usable && profile ? toRequest(profile) : null;
  const result = useCallAssessment(callId, usable, request ? JSON.stringify(request) : '');
  const doc = usable && profile ? fitOf(facts, profile) : null;

  if (!usable || !profile) {
    return (
      <section aria-labelledby={`readiness-${callId}`} className="flex flex-col gap-3">
        <H id={`readiness-${callId}`} className="m-0 text-h4">Your readiness for this call</H>
        <p className="m-0 text-body">
          Answer five short questions about your company, and this page will show whether the rules of this call and of its programme allow you to apply,
          what you would still need, and whether you can get it before the deadline. It takes about three minutes. Your answers stay in this browser.
        </p>
        <Button href="/readiness" iconRight={ArrowRight} className="self-start">Start the readiness check</Button>
      </section>
    );
  }

  const answer = result.state === 'done' ? result.data.call : null;
  const timings = answer?.timings ?? [];
  const fit: Fit | null = doc ? doc.fit : null;
  return (
    <section aria-labelledby={`readiness-${callId}`} className="flex flex-col gap-4">
      <H id={`readiness-${callId}`} className="m-0 text-h4">Your readiness for this call</H>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="m-0 text-small text-ink-muted">
          From the profile saved in this browser{profile.name ? <> ({profile.name})</> : null}. The answers are not stored on our server.
          {!isFinished(profile) && ' The profile is not finished, so some rules cannot be judged yet.'}
        </p>
        <Button href="/readiness" variant="secondary" icon={Pencil}>Change my answers</Button>
      </div>

      {result.state === 'done' && <p className="m-0 text-body font-semibold">{callSummary(fit, timings)}</p>}

      <div className="flex flex-col gap-2">
        <h4 className="m-0 text-label">The rules read from this call’s document: {doc ? FIT_WORD[doc.fit] : 'not compared'}</h4>
        {doc?.result ? (
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {doc.result.lines.map((l) => (
              <li key={l.key} className={ROW}>
                <span><strong>{l.label}: {l.verdict === 'yes' ? 'Allowed' : l.verdict === 'no' ? 'Not allowed' : 'Check'}.</strong> {l.reason}</span>
                {l.quote && <q className="text-small italic text-ink-muted">{l.quote}</q>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-small text-ink-muted">
            {facts ? 'None of the rules read from the document concerns what your profile says.' : 'The rules of this call have not been read, so there is nothing to compare your profile with. Read the source’s own text before you apply.'}
          </p>
        )}
        {doc && doc.conditions.length > 0 && (
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {doc.conditions.map((c) => <li key={c} className="text-body"><strong>Asked of every applicant.</strong> {c}</li>)}
          </ul>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="m-0 text-label">The programme’s rules, and the time left</h4>
        {(result.state === 'loading' || result.state === 'idle') && <Loading />}
        {result.state === 'error' && (
          <p role="alert" className="m-0 text-body">{result.message} <button type="button" onClick={result.retry} className="font-semibold underline">Try again</button></p>
        )}
        {result.state === 'done' && answer && (
          answer.covered && timings.length > 0 ? (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {timings.map((t) => <Timing key={t.programme} t={t} a={result.data.assessments.find((x) => x.programme === t.programme)} data={result.data} />)}
            </ul>
          ) : (
            <p className="m-0 text-body text-ink-muted">{answer.text ?? 'No readiness rules are encoded for the programme of this call, so no verdict is given.'}</p>
          )
        )}
        {result.state === 'done' && (
          <p className="m-0 text-small text-ink-muted">
            {result.data.notice} Rules last reviewed on {result.data.rulesReviewed.slice(0, 10)}. <Link href="/readiness/results" className="font-semibold">All programmes</Link>.
          </p>
        )}
      </div>
    </section>
  );
}
