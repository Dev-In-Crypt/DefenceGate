'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, ArrowRight, Download, Trash2, Upload } from 'lucide-react';
import { BUYER_COUNTRIES } from '@/lib/taxonomy';
import { STATUS_LABEL, exportProfile, firstStepToAnswer, importProfile, pctProblem, unanswered, visibleCodes, type Profile, type Status } from '@/lib/profile';
import { requirementSlug } from '@/lib/readiness';
import { cn } from '@/lib/utils';
import { Callout } from '@/components/dg/blocks';
import { CARD_PADDING, CARD_SURFACE } from '@/components/dg/card';
import { Button } from '@/components/dg/button';
import { Choice, Fieldset, Select, TextInput } from '@/components/dg/form';
import { useProfile } from './use-readiness';

export interface WizardRequirement { code: string; name: string; summary: string }

const COUNTRY_OPTIONS = [
  ...Object.entries({ ...BUYER_COUNTRIES, LI: 'Liechtenstein', UA: 'Ukraine', TR: 'Türkiye', US: 'United States' })
    .map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, 'en')),
  { value: 'XX', label: 'Another country (not listed)' },
];
const SIZE_OPTIONS = [
  { value: 'micro', label: 'Micro' }, { value: 'small', label: 'Small' }, { value: 'medium', label: 'Medium' }, { value: 'large', label: 'Large' },
];
const STEPS = ['Your company', 'Ownership and control', 'Products and regime', 'Certifications held', 'Classified work and exports'] as const;

/** Three radios in a fieldset: the shape of most questions. An `error` is tied to the group and marks its radios invalid. */
function Radios<T extends string>({ legend, hint, name, value, options, onChange, error }: {
  legend: string; hint?: string; name: string; value: T | ''; options: { value: T; label: string; hint?: string }[]; onChange: (v: T) => void; error?: string;
}) {
  return (
    <Fieldset id={`q-${name}`} legend={legend} hint={hint} error={error}>
      {options.map((o) => (
        <Choice key={o.value} type="radio" name={name} label={o.label} hint={o.hint} checked={value === o.value} onChange={() => onChange(o.value)}
          aria-invalid={error ? true : undefined} />
      ))}
    </Fieldset>
  );
}

const YES_NO_UNSURE = [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }, { value: 'unsure', label: 'I am not sure' }] as const;

export function Wizard({ requirements }: { requirements: WizardRequirement[] }) {
  const router = useRouter();
  const { profile, ready, update, clear, stored } = useProfile();
  const [step, setStep] = useState<number | null>(null);
  const [needCountry, setNeedCountry] = useState(false);
  const [needForm, setNeedForm] = useState(false);
  const [needManagement, setNeedManagement] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [notice, setNotice] = useState('');
  // After a step change or a refused "Next", focus goes where the visitor's attention must be (U16), not stays on the button.
  const [focusTarget, setFocusTarget] = useState<'heading' | 'error' | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const clearRef = useRef<HTMLButtonElement>(null);
  const keepRef = useRef<HTMLButtonElement>(null);

  // `?step=3` (the link under "answers are missing" on the results) opens that step.
  useEffect(() => {
    const n = Number(new URLSearchParams(window.location.search).get('step'));
    if (Number.isInteger(n) && n >= 1 && n <= 5) setStep(n);
  }, []);
  useEffect(() => {
    if (focusTarget === null) return;
    if (focusTarget === 'heading') headingRef.current?.focus();
    else formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"], input[name="legal-form"]')?.focus();
    setFocusTarget(null);
  }, [focusTarget]);
  useEffect(() => { if (confirmClear) keepRef.current?.focus(); }, [confirmClear]);

  if (!ready || profile === null) {
    return <p role="status" className="m-0 text-body text-ink-muted">Loading your saved answers from this browser…</p>;
  }
  const missing = unanswered(profile);
  // A finished profile is changed where something is still unanswered; a profile in progress is resumed where it was left.
  const current = step ?? (profile.step >= 6 ? firstStepToAnswer(profile) : Math.min(Math.max(profile.step, 1), 5));
  const set = <K extends keyof Profile>(key: K, value: Profile[K]) => update((p) => ({ ...p, [key]: value }));
  const go = (n: number) => {
    setNeedCountry(false);
    setNeedForm(false);
    setNeedManagement(false);
    setStep(n);
    update((p) => ({ ...p, step: Math.max(p.step, n) }));
    setFocusTarget('heading');
  };
  const next = () => {
    if (current === 1 && (!profile.country || !profile.legalForm)) { setNeedCountry(!profile.country); setNeedForm(!profile.legalForm); setFocusTarget('error'); return; }
    // An answer that cannot be used is refused here, with its reason beside the field, and not dropped later (WP-53, T6).
    if (current === 2 && profile.management === 'other' && !profile.managementCountry) { setNeedManagement(true); setFocusTarget('error'); return; }
    if (current === 3 && pctProblem(profile.componentPct)) { setFocusTarget('error'); return; }
    if (current === 5) {
      update((p) => ({ ...p, step: 6 }));
      router.push('/readiness/results');
      return;
    }
    go(current + 1);
  };
  const byCode = new Map(requirements.map((r) => [r.code, r]));

  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="Progress" className="flex flex-col gap-2">
        <p className="m-0 text-small font-bold" aria-live="polite">Step {current} of 5: {STEPS[current - 1]}</p>
        <ol className="m-0 flex list-none gap-1 p-0" aria-label="Steps">
          {STEPS.map((title, i) => (
            <li key={title} className="flex-1">
              {/* A button 44 px high with the 8 px bar inside: any step can be reached, and the thin bar is not the only target. */}
              <button type="button" onClick={() => go(i + 1)} aria-current={i + 1 === current ? 'step' : undefined}
                className="flex min-h-11 w-full flex-col justify-center border-0 bg-transparent p-0">
                <span className={`block h-2 w-full rounded-pill ${i + 1 < current ? 'bg-primary' : i + 1 === current ? 'bg-ink' : 'bg-surface-inset'}`} />
                <span className="sr-only">Go to step {i + 1}: {title}{i + 1 < current ? ' (done)' : i + 1 === current ? ' (current)' : ''}</span>
              </button>
            </li>
          ))}
        </ol>
        {missing.length > 0 && profile.step >= 6 && (
          <details className="text-small">
            <summary className="inline-flex min-h-11 cursor-pointer items-center font-semibold">
              {missing.length === 1 ? '1 question has no answer yet' : `${missing.length} questions have no answer yet`}
            </summary>
            <ul className="m-0 flex list-none flex-col gap-0.5 p-0 pb-2">
              {missing.map((m) => (
                <li key={m.question}>
                  <button type="button" onClick={() => go(m.step)} className="inline-flex min-h-12 items-center border-0 bg-transparent p-0 text-left font-sans text-small text-link underline">
                    Step {m.step}: {m.question}
                  </button>
                </li>
              ))}
            </ul>
          </details>
        )}
      </nav>

      {!stored && (
        <p role="alert" className="m-0 rounded-md bg-surface-inset p-3 text-small">
          Your browser would not save the answers (private window or blocked storage). They are kept while this page is open and are lost when you leave it.
        </p>
      )}

      {/* The shape of a titled Card (step name in its own column from lg, the questions in one reading measure beside it); a form cannot be a Card, and the heading takes focus. */}
      <form ref={formRef} className={cn('card-titled min-w-0', CARD_SURFACE)} onSubmit={(e) => { e.preventDefault(); next(); }} aria-label={STEPS[current - 1]}>
        <div className="card-head flex min-h-14 items-center border-b border-line px-5 py-3 sm:px-6">
          <h2 ref={headingRef} tabIndex={-1} className="m-0 text-h3">{STEPS[current - 1]}</h2>
        </div>
        <div className={cn('card-body flex min-w-0 flex-col gap-6', CARD_PADDING)}>

        {current === 1 && (
          <div className="flex flex-col gap-4">
            <TextInput className="max-w-form" label="Company name (optional)" hint="Shown on your results page. It never leaves this browser." maxLength={120}
              value={profile.name} onChange={(e) => set('name', e.target.value)} autoComplete="organization" />
            <Select className="max-w-form" label="Size of the company (optional)" hint="Kept for your own summary. No rule reads it." placeholder="Choose" options={SIZE_OPTIONS}
              value={profile.sizeClass} onChange={(e) => set('sizeClass', e.target.value as Profile['sizeClass'])} />
            <Select className="max-w-form" label="Country where your company is established" hint="Where it is registered. Most rules start here." placeholder="Choose a country"
              options={COUNTRY_OPTIONS} value={profile.country} aria-required="true"
              error={needCountry ? 'Choose a country to go on.' : undefined}
              onChange={(e) => { setNeedCountry(false); set('country', e.target.value); }} />
            <Radios legend="What is the legal form of your organisation?" name="legal-form" value={profile.legalForm}
              hint="The regulations fund legal entities: legal persons, and entities without legal personality only on the conditions of the Financial Regulation."
              options={[
                { value: 'legal_person', label: 'A legal person, for example a company, a foundation or a public body' },
                { value: 'natural_person', label: 'A natural person, for example a sole trader acting in their own name' },
                { value: 'no_legal_personality', label: 'An entity without legal personality, for example some partnerships' },
              ]}
              error={needForm ? 'Choose the legal form to go on.' : undefined}
              onChange={(v) => { setNeedForm(false); set('legalForm', v); }} />
            <Radios legend="What kind of organisation are you? (optional)" name="applicant-kind" value={profile.applicantKind}
              hint="Only a few calls care: EDIP calls for common procurement are open to contracting authorities, international organisations, SEAPs and the European Defence Agency, not to companies. Leave it empty if you do not know; it is then never read as “a company”."
              options={[
                { value: 'company_or_research', label: 'A company or a research body, including a university' },
                { value: 'contracting_authority', label: 'A contracting authority, for example a ministry or a procurement agency' },
                { value: 'international_organisation', label: 'An international organisation' },
                { value: 'seap', label: 'A SEAP (structure for European armament programmes)' },
                { value: 'eda', label: 'The European Defence Agency' },
              ]}
              onChange={(v) => set('applicantKind', v)} />
          </div>
        )}

        {current === 2 && (
          <div className="flex flex-col gap-5">
            <Radios legend="Where are your company's executive management structures?" name="management"
              hint="The place from which the company is actually run."
              value={profile.management}
              options={[{ value: 'same', label: 'In the country where the company is established' }, { value: 'other', label: 'In another country' }]}
              onChange={(v) => { setNeedManagement(false); set('management', v); }} />
            {profile.management === 'other' && (
              <Select className="max-w-form" label="Country of the executive management" placeholder="Choose a country" options={COUNTRY_OPTIONS}
                value={profile.managementCountry} aria-required="true"
                error={needManagement && !profile.managementCountry ? 'Choose the country of the executive management to go on.' : undefined}
                onChange={(e) => { setNeedManagement(false); set('managementCountry', e.target.value); }} />
            )}
            <Radios legend="Is your company controlled by a country or an entity outside the EU?" name="control"
              hint="Think of the ultimate owners, not only the first shareholder. Control from an EEA EFTA state or Ukraine is treated differently by each programme."
              value={profile.control}
              options={[
                { value: 'no', label: 'No' },
                { value: 'ua_eea_only', label: 'Yes, but only by Ukraine or an EEA EFTA state (Iceland, Liechtenstein, Norway)' },
                { value: 'other', label: 'Yes, by another country or an entity from another country' },
                { value: 'unsure', label: 'I am not sure' },
              ]}
              onChange={(v) => set('control', v)} />
            {profile.country === 'UA' && (
              <Radios legend="Is your company established in an area of Ukraine that the Ukrainian government does not control?" name="occupied"
                value={profile.uaOccupied} options={[...YES_NO_UNSURE]} onChange={(v) => set('uaOccupied', v)} />
            )}
            {profile.country !== 'UA' && (
              <Radios legend="Does your planned consortium include a legal entity established in Ukraine, with its executive management structure there?" name="ua-partner"
                hint="The Ukraine Support Instrument asks for one: an action must be carried out by, or with the involvement of, Ukraine or such an entity. Leave it empty if you do not know yet; it is then never read as “no”."
                value={profile.uaPartner} options={[...YES_NO_UNSURE]} onChange={(v) => set('uaPartner', v)} />
            )}
            <Radios legend="Does a SEAP (structure for European armament programmes) take part in your planned consortium?" name="seap-partner"
              hint="Some EDIP calls for industrial reinforcement ask for at least three independent entities unless a SEAP takes part. Leave it empty if you do not know yet; it is then never read as “no”."
              value={profile.seapPartner} options={[...YES_NO_UNSURE]} onChange={(v) => set('seapPartner', v)} />
          </div>
        )}

        {current === 3 && (
          <div className="flex flex-col gap-5">
            <Callout title="Two export regimes, and why we ask">
              <p className="m-0">Dual-use items can be used for both civil and military purposes and are listed in Annex I of Regulation (EU) 2021/821. Military goods are on the Common Military List. A product can be in the military regime and not the dual-use one.</p>
              <p className="m-0">Customs codes do not settle it. You decide from your product&rsquo;s datasheet and, if unsure, ask the competent authority. This service asks which regime applies, never what the product does.</p>
            </Callout>
            <Radios legend="Which regime is your main product in?" name="regime" value={profile.regime}
              options={[
                { value: 'dual_use', label: 'Dual-use (on the Annex I list)' },
                { value: 'military', label: 'Military (on the Common Military List)' },
                { value: 'none', label: 'Neither' },
                { value: 'unknown', label: 'I do not know yet' },
              ]}
              onChange={(v) => set('regime', v)} />
            <TextInput className="max-w-form" label="Share of component cost from outside the EU, the EEA EFTA states and Ukraine (%)" inputMode="decimal" maxLength={12}
              hint="For the main end product you would supply, as a share of the estimated cost of its components, not of the contract value. Leave empty if you do not know."
              value={profile.componentPct} onChange={(e) => set('componentPct', e.target.value)}
              error={pctProblem(profile.componentPct) ?? undefined} />
            <Radios legend="Does any component come from a third country that contravenes the security and defence interests of the Union and its Member States?" name="restricted"
              hint="The regulation gives no list of such countries. If you are unsure, ask the contracting authority."
              value={profile.restricted} options={[...YES_NO_UNSURE]} onChange={(v) => set('restricted', v)} />
            <Radios legend="Do any components of that product originate in Ukraine or in an EEA EFTA state (Iceland, Liechtenstein, Norway)?" name="ua-eea-components"
              hint="EDIP and the Ukraine Support Instrument count components from these places differently from SAFE, so the 35 % limit cannot be judged without this answer."
              value={profile.uaEeaComponents} options={[...YES_NO_UNSURE]} onChange={(v) => set('uaEeaComponents', v)} />
            <Radios legend="In a SAFE-supported procurement, what would your role be?" name="safe-role" value={profile.safeRole}
              hint="SAFE binds the contractor and the subcontractors involved in the common procurement: those that provide critical inputs, are allocated at least 15 % of the value of the contract and need access to classified information. A supplier below that is not bound by its rules on establishment and control."
              options={[
                { value: 'contractor', label: 'We would be the contractor' },
                { value: 'subcontractor_involved', label: 'We would be a subcontractor of that kind (critical inputs, at least 15 % of the contract value, access to classified information)' },
                { value: 'other_supplier', label: 'We would supply components or services below that level' },
                { value: 'unsure', label: 'I am not sure' },
              ]}
              onChange={(v) => set('safeRole', v)} />
          </div>
        )}

        {current === 4 && (
          <div className="flex flex-col gap-4">
            <p className="m-0 max-w-prose text-small text-ink-muted">
              Say what you already hold. Anything you leave as it is counts as not held. “Not applicable to us” leaves that rule out of your result; it does not count as holding it.
            </p>
            {visibleCodes(profile.country).map((code) => {
              const r = byCode.get(code);
              return (
                <div key={code} className="flex flex-col gap-1">
                  <Select className="max-w-form" label={r?.name ?? code} hint={r?.summary} options={(Object.keys(STATUS_LABEL) as Status[]).map((s) => ({ value: s, label: STATUS_LABEL[s] }))}
                    value={profile.statuses[code] ?? 'not_held'}
                    onChange={(e) => update((p) => ({ ...p, statuses: { ...p.statuses, [code]: e.target.value as Status } }))} />
                  <a href={`/requirements/${requirementSlug(code)}`} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center text-small font-semibold">
                    What is this? (opens in a new tab)
                  </a>
                </div>
              );
            })}
          </div>
        )}

        {current === 5 && (
          <div className="flex flex-col gap-5">
            <Radios legend="Will you handle classified information in a contract?" name="classified" value={profile.classified}
              options={[...YES_NO_UNSURE]} onChange={(v) => set('classified', v)} />
            <Radios legend="Do you export, or plan to export, your product?" name="export" value={profile.exportIntent}
              options={[
                { value: 'none', label: 'No' },
                { value: 'within_eu', label: 'Yes, to other EU countries' },
                { value: 'outside_eu', label: 'Yes, outside the EU' },
                { value: 'unsure', label: 'Not sure yet' },
              ]}
              onChange={(v) => set('exportIntent', v)} />
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          {current > 1 ? <Button variant="secondary" icon={ArrowLeft} onClick={() => go(current - 1)}>Back</Button> : <span />}
          <Button type="submit" iconRight={ArrowRight}>{current === 5 ? 'See my results' : 'Next'}</Button>
        </div>
        </div>
      </form>

      <div className="flex flex-col gap-3 text-small text-ink-muted">
        <p className="m-0 flex flex-wrap items-center gap-x-4">
          Answers are saved in this browser as you go.
          {!confirmClear && (
            <button ref={clearRef} type="button" onClick={() => setConfirmClear(true)}
              className="inline-flex min-h-11 items-center gap-1 border-0 bg-transparent p-0 font-sans text-small font-bold text-link underline">
              <Trash2 size={16} strokeWidth={1.75} aria-hidden="true" className="shrink-0" />Clear my answers
            </button>
          )}
        </p>
        {confirmClear && (
          <div role="alertdialog" aria-label="Clear my answers" aria-describedby="clear-text" className="flex flex-col gap-2 rounded-md bg-surface-inset p-4 text-ink">
            <p id="clear-text" className="m-0 font-semibold">Clear every answer saved in this browser? This cannot be undone. Save them to a file first if you may need them again.</p>
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" onClick={() => { clear(); setStep(1); setConfirmClear(false); setNotice('Your answers were cleared from this browser.'); setFocusTarget('heading'); }}>Yes, clear them</Button>
              <button ref={keepRef} type="button" onClick={() => { setConfirmClear(false); window.setTimeout(() => clearRef.current?.focus(), 0); }}
                className="inline-flex min-h-11 items-center rounded-pill border-strong border-ink bg-surface px-5 font-sans text-small font-bold text-ink">Keep my answers</button>
            </div>
          </div>
        )}
        {notice && <p role="status" className="m-0 font-semibold text-ink">{notice}</p>}
        <Keep profile={profile} onImport={(p) => { update(() => p); setStep(null); setNotice('Answers loaded from the file. They replace the ones that were here.'); }} />
      </div>
    </div>
  );
}

/**
 * Taking the answers elsewhere (U7): a consultant who checks a second client must not overwrite the first, and an answer set
 * should survive a cleared browser. The text is the block the browser stores; a file or a paste is checked field by field on the way in.
 */
function Keep({ profile, onImport }: { profile: Profile; onImport: (p: Profile) => void }) {
  const [text, setText] = useState('');
  const [problem, setProblem] = useState('');
  const [copied, setCopied] = useState(false);
  const block = exportProfile(profile);
  const download = () => {
    const url = URL.createObjectURL(new Blob([block], { type: 'application/json' }));
    const a = document.createElement('a');
    const who = profile.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
    a.href = url;
    a.download = `defencegate-answers${who ? `-${who}` : ''}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };
  const load = (raw: string) => {
    const r = importProfile(raw);
    if (!r.ok) { setProblem(r.reason); return; }
    setProblem('');
    setText('');
    onImport(r.profile);
  };
  return (
    <details>
      <summary className="inline-flex min-h-11 cursor-pointer items-center font-bold text-ink">Keep my answers in a file, or load answers from one</summary>
      <div className="flex flex-col gap-3 pb-2">
        <p className="m-0 max-w-prose">
          The file holds exactly what this browser holds, including the company name if you entered one. Use it to check another company without losing this one,
          or to move to another computer. Nothing is sent to our server.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button type="button" variant="secondary" icon={Download} onClick={download}>Download my answers</Button>
          <Button type="button" variant="secondary" onClick={() => { void navigator.clipboard?.writeText(block).then(() => setCopied(true), () => setCopied(false)); }}>Copy my answers</Button>
        </div>
        {copied && <p role="status" className="m-0 font-semibold text-ink">Copied.</p>}
        <label className="flex flex-col gap-1 text-label text-ink">Load answers from a file
          <input type="file" accept="application/json,.json" className="min-h-11 font-sans text-small"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = '';
              if (!f) return;
              if (f.size > 20_000) setProblem('That file is too large to be a set of answers from this site.');
              else void f.text().then(load);
            }} />
        </label>
        <label className="flex flex-col gap-1 text-label text-ink">Or paste the copied answers here
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={20_000} spellCheck={false}
            className="max-w-form rounded-md border-strong border-input-edge bg-surface p-3 font-mono text-small text-ink" />
        </label>
        <div><Button type="button" variant="secondary" icon={Upload} onClick={() => load(text)} disabled={text.trim() === ''}>Load the pasted answers</Button></div>
        {problem && <p role="alert" className="m-0 font-semibold text-alert">{problem}</p>}
      </div>
    </details>
  );
}
