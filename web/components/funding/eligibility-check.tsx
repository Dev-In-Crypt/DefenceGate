'use client';

import { useState } from 'react';
import { CircleAlert, CircleCheck, CircleX } from 'lucide-react';
import { BUYER_COUNTRIES } from '@/lib/taxonomy';
import { check, factText, FACT_LABELS, SCOPE_WORDS, type EligibilityFacts, type Profile, type Verdict } from '@/lib/eligibility-check';
import type { EligibilitySourceInfo } from '@/lib/types';
import { safeHttpUrl } from '@/lib/safe-url';
import { Select } from '@/components/dg/form';
import { Icon } from '@/components/dg/icon';
import { cn } from '@/lib/utils';

const COUNTRY_OPTIONS = [...Object.entries({ ...BUYER_COUNTRIES, UA: 'Ukraine' })
  .map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label)), { value: 'XX', label: 'Another country' }];
const TYPES = [
  { value: 'sme', label: 'Small or medium enterprise' }, { value: 'large', label: 'Large company' },
  { value: 'public', label: 'Public body' }, { value: 'university', label: 'University or research organisation' },
  { value: 'individual', label: 'Individual (natural person)' },
];
const TRI = [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }, { value: 'unsure', label: 'Not sure' }];

const VERDICT: Record<Verdict, { icon: typeof CircleCheck; word: string; cls: string }> = {
  yes: { icon: CircleCheck, word: 'You can apply', cls: 'text-ink' },
  check: { icon: CircleAlert, word: 'Check before you apply', cls: 'text-ink' },
  no: { icon: CircleX, word: 'You cannot apply', cls: 'text-ink' },
};
const WORD: Record<Verdict, string> = { yes: 'Allowed', check: 'Check', no: 'Not allowed' };

export function EligibilityCheck({ facts, documentUrl, readAt, basis = 'call_document', sources = [] }: {
  facts: EligibilityFacts; documentUrl: string | null; readAt: string; basis?: 'call_document' | 'work_programme'; sources?: EligibilitySourceInfo[];
}) {
  const [p, setP] = useState<Profile>({ country: '', orgType: '', hasPartners: '', controlledAbroad: '' });
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setP((x) => ({ ...x, [k]: v }));
  const result = check(facts, p);
  const answered = result.lines.length > 0;
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
      ) : (
        <p className="m-0 text-small text-ink-muted">
          Read automatically from the call document on {readAt}. Each line shows the document’s own sentence. The document is authoritative and this is not legal advice.
        </p>
      )}

      <dl className="m-0 flex flex-col">
        {shown.map((k, i) => {
          const f = facts[k]!;
          return (
            <div key={k} className={cn('flex flex-col gap-1 py-3 sm:flex-row sm:gap-6', i < shown.length - 1 && 'border-b border-line')}>
              <dt className="text-body font-semibold sm:w-64 sm:shrink-0">{FACT_LABELS[k]}</dt>
              <dd className="m-0 flex min-w-0 flex-col gap-1 text-body">
                <span>{factText(f)}</span>
                {fromProgramme && f.scope && <span className="text-label font-bold text-ink">{SCOPE_WORDS[f.scope]}</span>}
                {f.note && <span className="text-small text-ink-muted">{f.note}</span>}
                <q className="text-small italic text-ink-muted">{f.quote}</q>
              </dd>
            </div>
          );
        })}
      </dl>

      <form className="flex flex-col gap-3 rounded-md border border-line p-4" onSubmit={(e) => e.preventDefault()} aria-label="Check your company against this call">
        <h3 className="m-0 text-h4">Check your company</h3>
        <p className="m-0 text-small text-ink-muted">Your answers stay in this page. Nothing is sent or saved.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Select label="Where is your organisation established?" placeholder="Choose" options={COUNTRY_OPTIONS} value={p.country} onChange={(e) => set('country', e.target.value)} />
          <Select label="What kind of organisation?" placeholder="Choose" options={TYPES} value={p.orgType} onChange={(e) => set('orgType', e.target.value as Profile['orgType'])} />
          <Select label="Do you already have consortium partners?" placeholder="Choose" options={TRI} value={p.hasPartners} onChange={(e) => set('hasPartners', e.target.value as Profile['hasPartners'])} />
          <Select label="Is your company controlled from outside the EU or associated countries?" placeholder="Choose" options={TRI} value={p.controlledAbroad} onChange={(e) => set('controlledAbroad', e.target.value as Profile['controlledAbroad'])} />
        </div>
      </form>

      <div aria-live="polite" className="flex flex-col gap-3">
        {answered ? (
          <>
            <p className={cn('m-0 flex items-center gap-2 text-h4', V.cls)}><Icon icon={V.icon} size="button" />{V.word}</p>
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {result.lines.map((l) => (
                <li key={l.key} className="flex flex-col gap-0.5 text-body">
                  <span><strong>{l.label}: {WORD[l.verdict]}.</strong> {l.reason}</span>
                  {l.quote && <q className="text-small italic text-ink-muted">{l.quote}</q>}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="m-0 text-small text-ink-muted">Answer the questions above to see what the document says about your company.</p>
        )}
      </div>

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
