'use client';

import { CircleAlert, CircleCheck, CircleX } from 'lucide-react';
import { BUYER_COUNTRIES } from '@/lib/taxonomy';
import { consortiumUnclear, factDisplay, FACT_LABELS, SCOPE_WORDS, sizeRule, type CallContext, type EligibilityFacts, type Profile, type Verdict } from '@/lib/eligibility-check';
import { asksUaPartner, fitLabel, linesSummary, shownFit, verdictLines, type Answers } from '@/lib/fit';
import { useFit } from '@/lib/fit-hooks';
import { fitFor, isLoaded, lookupFailed } from '@/lib/fit-store';
import { cleanQuote } from '@/lib/quote';
import type { Call, EligibilitySourceInfo, RulesApply } from '@/lib/types';
import { safeHttpUrl } from '@/lib/safe-url';
import { Select } from '@/components/dg/form';
import { Icon } from '@/components/dg/icon';
import { pageFit, usePageCase } from './apply-summary';
import { cn } from '@/lib/utils';
import { CallReadiness, FactsContext } from './call-readiness';

const COUNTRY_OPTIONS = [...Object.entries({ ...BUYER_COUNTRIES, LI: 'Liechtenstein', UA: 'Ukraine', TR: 'Türkiye', US: 'United States' })
  .map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label)), { value: 'XX', label: 'Another country' }];
const TYPES = [
  { value: 'sme', label: 'Small or medium enterprise' }, { value: 'large', label: 'Large company' },
  { value: 'public', label: 'Public body' }, { value: 'university', label: 'University or research organisation' },
  { value: 'individual', label: 'Individual (natural person)' },
];
const TRI = [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }, { value: 'unsure', label: 'Not sure' }];
// the bands of the readiness check (lib/eligibility-check.ts BAND_RANGE)
const BANDS = [
  { value: 'lt50', label: 'Fewer than 50' }, { value: '50_249', label: '50 to 249' }, { value: '250_499', label: '250 to 499' },
  { value: '500_1999', label: '500 to 1,999' }, { value: '2000plus', label: '2,000 or more' },
];
const CONTROLLERS = [
  { value: 'ua', label: 'Ukraine' }, { value: 'eea', label: 'Iceland, Liechtenstein or Norway' }, { value: 'cn', label: 'China' },
  { value: 'ru_by', label: 'Russia or Belarus' }, { value: 'other_non_eu', label: 'Another country (for example the United States)' },
];

const VERDICT: Record<Verdict, { icon: typeof CircleCheck; word: string; cls: string }> = {
  yes: { icon: CircleCheck, word: 'Nothing in the document excludes you so far', cls: 'text-ink' },
  check: { icon: CircleAlert, word: 'Check before you apply', cls: 'text-ink' },
  no: { icon: CircleX, word: 'The document appears to exclude you: read the quoted sentence', cls: 'text-ink' },
};
const WORD: Record<Verdict, string> = { yes: 'Allowed', check: 'Check', no: 'Not allowed' };

/** WP-91: the sentence on Ukraine's non-government-controlled areas concerns a Ukrainian company only; for any other country it is left out. */
const NGCA = /non-government[- ]controlled areas? of Ukraine/i;
function shownNote(key: string, note: string, country: string): string {
  if (key !== 'eligible_countries' || country === 'UA') return note;
  return (note.match(/[^.;!?]+[.;!?]*/g) ?? []).map((s) => s.trim()).filter((s) => s && !NGCA.test(s)).join(' ');
}

export function EligibilityCheck({ facts, documentUrl, readAt, basis = 'call_document', sources = [], callId, closed = false, ctx, rulesApply = null }: {
  facts: EligibilityFacts; documentUrl: string | null; readAt: string; basis?: 'call_document' | 'work_programme' | 'call_page'; sources?: EligibilitySourceInfo[];
  /** WP-109: the programme's rules the API evaluated for each group of countries, so the form says what the first screen says. */
  rulesApply?: RulesApply | null;
  /** WP-93: the call's programme and topic, so that "associated countries" are read as the list badge reads them. */
  ctx?: CallContext;
  /** The call's id: with it, the panel also shows "Your readiness for this call" from the saved profile (WP-32). */
  callId?: string;
  /** The call has closed: its rules are listed for reference and there is no verdict, no form and no readiness block. */
  closed?: boolean;
}) {
  // WP-109 (one verdict per call page in every state): the form and the first screen share one case (`usePageCase`). Untouched, it is the
  // saved profile's (U4: the form asked its answers again, empty) and the verdict is the profile's (lib/fit.ts callFit, the list badge's);
  // changed, here or at the top, it is another case, judged by `answersFit` on the same facts and the programme's rules, the top's verdict too.
  // What only the saved profile knows (`more`, its kind, its investor) no longer applies to a changed case (WP-53, WP-93).
  const pc = usePageCase(callId ?? '');
  const p = pc.answers;
  const edited = !pc.profileMode;
  const held = pc.profileMode;
  const set = <K extends keyof Answers>(k: K, v: Answers[K]) => pc.set({ [k]: v, more: undefined, kind: undefined, size: undefined, investor: undefined } as Partial<Answers>);
  const store = useFit(callId ?? '');
  const loaded = callId && pc.profileMode && store.hasProfile && isLoaded(callId) && !lookupFailed(callId) ? fitFor(callId) : null;
  // a profile verdict with nothing to compare ("Rules not read" in the list) leaves the form to the facts on this page, as before
  const one = loaded && loaded.fit !== 'unknown' ? loaded : null;
  const fit = pageFit({ programme: ctx?.programme ?? '', topicId: ctx?.topic ?? '', rulesApply, documentEligibility: { facts } as Call['documentEligibility'] }, pc, one);
  const result = { verdict: (shownFit(fit) === 'no' ? 'no' : shownFit(fit) === 'yes' ? 'yes' : 'check') as Verdict, lines: verdictLines(fit) };
  const answered = result.lines.length > 0;
  const word = fitLabel(fit).word;
  // the questions this call needs beyond the four (WP-109): the staff count for a size rule, who controls the company for a restriction
  // that names countries, a Ukrainian partner where the programme's rules ask for one
  const asksSize = Boolean(sizeRule(facts) || facts.max_group_headcount);
  const asksController = Boolean(facts.ownership_control_restriction?.value === true && p.controlledAbroad === 'yes');
  const asksUa = asksUaPartner({ rulesApply }, p.country);
  const shown = Object.keys(FACT_LABELS).filter((k) => facts[k]);
  const doc = documentUrl ? safeHttpUrl(documentUrl) : null;
  const fromProgramme = basis === 'work_programme';
  const V = VERDICT[result.verdict];

  return (
    <div className="flex flex-col gap-5">
      {fromProgramme ? (
        <p className="m-0 text-small text-ink-muted">
          This call has no call document of its own. The rules below were read automatically on {readAt} from the work programme’s general annexes
          (they apply to every call of the programme, and the topic may change them) and from this topic’s own conditions. Each line says which, and shows
          the text’s own sentence. The official texts are authoritative and this is not legal advice.
        </p>
      ) : basis === 'call_page' ? (
        <p className="m-0 text-small text-ink-muted">
          Read automatically on {readAt} from the agency’s call page, which states these rules in fixed words; its text is not reproduced here. Only these rules were
          read: the page is authoritative and this is not legal advice.
        </p>
      ) : (
        <p className="m-0 text-small text-ink-muted">
          Read automatically from the call document on {readAt}. Each line shows the document’s own sentence. The document is authoritative and this is not legal advice.
        </p>
      )}

      <dl className="m-0 flex flex-col">
        {shown.map((k, i) => {
          const f = facts[k]!;
          return (
            <div key={k} className={cn('flex flex-col gap-1 py-3', i < shown.length - 1 && 'border-b border-line')}>
              <dt className="text-body font-semibold">{FACT_LABELS[k]}</dt>
              <dd className="m-0 flex min-w-0 flex-col gap-1 text-body">
                <span className={k === 'consortium_required' && consortiumUnclear(facts) ? 'font-semibold' : undefined}>{factDisplay(k, facts)}</span>
                {fromProgramme && f.scope && <span className="text-label font-bold text-ink">{SCOPE_WORDS[f.scope]}</span>}
                {f.note && shownNote(k, f.note, p.country) && <span className="text-small text-ink-muted">{shownNote(k, f.note, p.country)}</span>}
                {f.quote ? <q className="text-small text-ink-muted">{cleanQuote(f.quote)}</q>
                  : <span className="text-small text-ink-muted">Read from the agency’s call page; its text is not reproduced here.</span>}
              </dd>
            </div>
          );
        })}
      </dl>

      {closed ? (
        <p role="status" className="m-0 rounded-md bg-surface-inset px-4 py-3 text-small text-ink">
          This call is closed, so there is no verdict. The rules above are listed for reference, as read from the document.
        </p>
      ) : (
        <>
      <form className="flex flex-col gap-3 rounded-md border border-line p-4" onSubmit={(e) => e.preventDefault()} aria-label="Check your company against this call">
        <h3 className="m-0 text-h4">Check your company</h3>
        <p className="m-0 text-small text-ink-muted">
          {held && !edited
            ? 'Filled in from the profile saved in this browser: country, size and control. Change an answer to try another case. Nothing is sent or saved from here. Your profile does not say whether you already have consortium partners, so that one is yours to answer.'
            : 'Your answers stay in this page. Nothing is sent or saved.'}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Select label="Where is your organisation established?" placeholder="Choose" options={COUNTRY_OPTIONS} value={p.country} onChange={(e) => set('country', e.target.value)} />
          <Select label="What kind of organisation?" placeholder="Choose" options={TYPES} value={p.orgType} onChange={(e) => set('orgType', e.target.value as Profile['orgType'])} />
          <Select label="Do you already have consortium partners?" placeholder="Choose" options={TRI} value={p.hasPartners} onChange={(e) => set('hasPartners', e.target.value as Profile['hasPartners'])} />
          <Select label="Is your company controlled from outside the EU or associated countries?" placeholder="Choose" options={TRI} value={p.controlledAbroad} onChange={(e) => set('controlledAbroad', e.target.value as Profile['controlledAbroad'])} />
          {asksSize && <Select label="Staff, counted with your group (linked enterprises)" placeholder="Choose" options={BANDS} value={p.headcount ?? ''} onChange={(e) => set('headcount', e.target.value)} />}
          {asksController && <Select label="From which country is it controlled?" placeholder="Choose" options={CONTROLLERS} value={p.controller ?? ''} onChange={(e) => set('controller', e.target.value as Answers['controller'])} />}
          {asksUa && <Select label="Does a legal entity established in Ukraine, with its executive management there, take part?" placeholder="Choose" options={TRI} value={p.uaPartner ?? ''} onChange={(e) => set('uaPartner', e.target.value as Answers['uaPartner'])} />}
        </div>
      </form>

      <div aria-live="polite" className="flex flex-col gap-3">
        {answered ? (
          <>
            <p className={cn('m-0 flex items-center gap-2 text-h4', V.cls)} data-form-verdict={shownFit(fit)}><Icon icon={V.icon} size="button" />{V.word}</p>
            {/* WP-109: the same words as the first screen and the list badge */}
            <p className="m-0 text-body font-semibold" data-form-word>{word}</p>
            <p className="m-0 text-body font-semibold">{linesSummary(result.lines)}</p>
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {result.lines.map((l) => (
                <li key={l.key} className="flex flex-col gap-0.5 text-body">
                  <span><strong>{l.label}: {WORD[l.verdict]}.</strong> {l.reason}</span>
                  {l.quote && <q className="text-small text-ink-muted">{cleanQuote(l.quote)}</q>}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="m-0 text-small text-ink-muted">Answer the questions above to see what the document says about your company.</p>
        )}
      </div>

      {callId && (
        <FactsContext.Provider value={facts}>
          <div className="border-t border-line pt-5"><CallReadiness callId={callId} /></div>
        </FactsContext.Provider>
      )}
        </>
      )}

      {fromProgramme ? (
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-small">
          {sources.filter((s) => s.url && safeHttpUrl(s.url)).map((s) => (
            <li key={s.url}><a href={safeHttpUrl(s.url!) ?? '#'} target="_blank" rel="noopener noreferrer" className="font-semibold underline">Open: {s.label}</a></li>
          ))}
        </ul>
      ) : (
        doc && <p className="m-0 text-small"><a href={doc} target="_blank" rel="noopener noreferrer" className="font-semibold underline">Open the call document</a></p>
      )}
    </div>
  );
}
