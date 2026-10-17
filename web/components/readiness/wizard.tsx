'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, ArrowRight, Trash2 } from 'lucide-react';
import { BUYER_COUNTRIES } from '@/lib/taxonomy';
import { STATUS_LABEL, visibleCodes, type Profile, type Status } from '@/lib/profile';
import { requirementSlug } from '@/lib/readiness';
import { Callout } from '@/components/dg/blocks';
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

/** Three radios in a fieldset: the shape of most questions. */
function Radios<T extends string>({ legend, hint, name, value, options, onChange }: {
  legend: string; hint?: string; name: string; value: T | ''; options: { value: T; label: string; hint?: string }[]; onChange: (v: T) => void;
}) {
  return (
    <Fieldset legend={legend}>
      {hint && <p className="m-0 max-w-[70ch] text-small text-ink-muted">{hint}</p>}
      {options.map((o) => (
        <Choice key={o.value} type="radio" name={name} label={o.label} hint={o.hint} checked={value === o.value} onChange={() => onChange(o.value)} />
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

  if (!ready || profile === null) {
    return <p role="status" className="m-0 text-body text-ink-muted">Loading your saved answers from this browser…</p>;
  }
  const current = step ?? Math.min(Math.max(profile.step, 1), 5);
  const set = <K extends keyof Profile>(key: K, value: Profile[K]) => update((p) => ({ ...p, [key]: value }));
  const go = (n: number) => {
    setNeedCountry(false);
    setStep(n);
    update((p) => ({ ...p, step: Math.max(p.step, n) }));
  };
  const next = () => {
    if (current === 1 && !profile.country) { setNeedCountry(true); return; }
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
            <li key={title} className="flex-1" aria-current={i + 1 === current ? 'step' : undefined}>
              <span className={`block h-2 rounded-pill ${i + 1 < current ? 'bg-primary' : i + 1 === current ? 'bg-ink' : 'bg-surface-inset'}`} />
              <span className="sr-only">{title}{i + 1 < current ? ' (done)' : i + 1 === current ? ' (current)' : ''}</span>
            </li>
          ))}
        </ol>
      </nav>

      {!stored && (
        <p role="alert" className="m-0 rounded-md bg-surface-inset p-3 text-small">
          Your browser would not save the answers (private window or blocked storage). They are kept while this page is open and are lost when you leave it.
        </p>
      )}

      <form className="flex flex-col gap-6 rounded-lg bg-surface p-5 sm:p-6" onSubmit={(e) => { e.preventDefault(); next(); }} aria-label={STEPS[current - 1]}>
        <h2 className="m-0 text-h3">{STEPS[current - 1]}</h2>

        {current === 1 && (
          <div className="flex flex-col gap-4">
            <TextInput label="Company name (optional)" hint="Shown on your results page. It never leaves this browser." maxLength={120}
              value={profile.name} onChange={(e) => set('name', e.target.value)} autoComplete="organization" />
            <Select label="Size of the company (optional)" hint="Kept for your own summary. No rule reads it." placeholder="Choose" options={SIZE_OPTIONS}
              value={profile.sizeClass} onChange={(e) => set('sizeClass', e.target.value as Profile['sizeClass'])} />
            <Select label="Country where your company is established" hint="Where it is registered. Most rules start here." placeholder="Choose a country"
              options={COUNTRY_OPTIONS} value={profile.country} aria-required="true"
              error={needCountry ? 'Choose a country to go on.' : undefined}
              onChange={(e) => { setNeedCountry(false); set('country', e.target.value); }} />
          </div>
        )}

        {current === 2 && (
          <div className="flex flex-col gap-5">
            <Radios legend="Where are your company's executive management structures?" name="management"
              hint="The place from which the company is actually run."
              value={profile.managementSameCountry ? 'same' : 'other'}
              options={[{ value: 'same', label: 'In the country where the company is established' }, { value: 'other', label: 'In another country' }]}
              onChange={(v) => set('managementSameCountry', v === 'same')} />
            {!profile.managementSameCountry && (
              <Select label="Country of the executive management" placeholder="Choose a country" options={COUNTRY_OPTIONS}
                value={profile.managementCountry} onChange={(e) => set('managementCountry', e.target.value)} />
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
            <TextInput label="Share of component cost from outside the EU, the EEA EFTA states and Ukraine (%)" inputMode="decimal" maxLength={6}
              hint="For the main end product you would supply, as a share of the estimated cost of its components, not of the contract value. Leave empty if you do not know."
              value={profile.componentPct} onChange={(e) => set('componentPct', e.target.value.replace(/[^0-9.,]/g, ''))} />
            <Radios legend="Does any component come from a third country that contravenes the security and defence interests of the Union and its Member States?" name="restricted"
              hint="The regulation gives no list of such countries. If you are unsure, ask the contracting authority."
              value={profile.restricted} options={[...YES_NO_UNSURE]} onChange={(v) => set('restricted', v)} />
          </div>
        )}

        {current === 4 && (
          <div className="flex flex-col gap-4">
            <p className="m-0 max-w-[70ch] text-small text-ink-muted">Say what you already hold. Anything you leave as it is counts as not held.</p>
            {visibleCodes(profile.country).map((code) => {
              const r = byCode.get(code);
              return (
                <div key={code} className="flex flex-col gap-1">
                  <Select label={r?.name ?? code} hint={r?.summary} options={(Object.keys(STATUS_LABEL) as Status[]).map((s) => ({ value: s, label: STATUS_LABEL[s] }))}
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
      </form>

      <p className="m-0 flex flex-wrap items-center gap-x-4 text-small text-ink-muted">
        Answers are saved in this browser as you go.
        <button type="button" onClick={() => { clear(); setStep(1); }}
          className="inline-flex min-h-11 items-center gap-1 border-0 bg-transparent p-0 font-sans text-small font-bold text-link underline">
          <Trash2 size={16} strokeWidth={1.75} aria-hidden="true" />Clear my answers
        </button>
      </p>
    </div>
  );
}
