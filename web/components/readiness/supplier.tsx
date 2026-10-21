'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, X } from 'lucide-react';
import { cpvDictionaryTitle, cpvSearch } from '@/lib/cpv';
import {
  CERTIFICATES, CPV_MAX, ES_QUESTIONS, PROCESSES, REGISTRATIONS, cpvProblem, holds, monthProblem, naceProblem, savedSupplier,
  supplierProblems, withHeld, type Holding, type Profile, type Supplier, type Tri,
} from '@/lib/profile';
import { cn } from '@/lib/utils';
import { CARD_PADDING, CARD_SURFACE } from '@/components/dg/card';
import { Button } from '@/components/dg/button';
import { Choice, Fieldset, Select, TextInput } from '@/components/dg/form';
import { COUNTRY_OPTIONS, Radios, SIZE_OPTIONS, YES_NO_UNSURE } from './wizard';
import { useProfile } from './use-readiness';

/** The autonomous communities and cities of Spain, by their ISO 3166-2 codes. */
export const ES_REGIONS = [
  ['ES-AN', 'Andalucía'], ['ES-AR', 'Aragón'], ['ES-AS', 'Asturias'], ['ES-IB', 'Illes Balears'], ['ES-CN', 'Canarias'], ['ES-CB', 'Cantabria'],
  ['ES-CL', 'Castilla y León'], ['ES-CM', 'Castilla-La Mancha'], ['ES-CT', 'Cataluña'], ['ES-VC', 'Comunitat Valenciana'], ['ES-EX', 'Extremadura'],
  ['ES-GA', 'Galicia'], ['ES-MD', 'Comunidad de Madrid'], ['ES-MC', 'Región de Murcia'], ['ES-NC', 'Comunidad Foral de Navarra'], ['ES-PV', 'País Vasco'],
  ['ES-RI', 'La Rioja'], ['ES-CE', 'Ceuta'], ['ES-ML', 'Melilla'],
].map(([value, label]) => ({ value, label }));

/** One block of the page: a card with its own heading (the shape of a wizard step). */
function Part({ title, id, children }: { title: string; id: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className={cn('min-w-0', CARD_SURFACE)}>
      <div className="flex min-h-14 items-center border-b border-line px-5 py-3 sm:px-6"><h2 id={id} className="m-0 text-h3">{title}</h2></div>
      <div className={cn('flex min-w-0 flex-col gap-5', CARD_PADDING)}>{children}</div>
    </section>
  );
}

/**
 * The supplier profile (WP-65): a parts or materials maker that wants to supply defence buyers. One page, saved in this browser as it is
 * filled in (the same block as the wizard: `dg.profile.v1`, version 3). Answers shared with the wizard (country, size, certificates,
 * classified information) are the same answers. Nothing is sent from here; the results page sends what the rules read.
 */
export function SupplierForm() {
  const router = useRouter();
  const { profile, ready, update, stored } = useProfile();
  const [tried, setTried] = useState(false);
  const summaryRef = useRef<HTMLDivElement>(null);
  const [focusSummary, setFocusSummary] = useState(0);
  useEffect(() => { if (focusSummary) summaryRef.current?.focus(); }, [focusSummary]);

  if (!ready || profile === null) return <p role="status" className="m-0 text-body text-ink-muted">Loading your saved answers from this browser…</p>;
  const s = profile.supplier;
  const es = profile.country === 'ES';
  const setS = <K extends keyof Supplier>(key: K, value: Supplier[K]) => update((p) => ({ ...p, supplier: { ...p.supplier, [key]: value } }));
  const answer = (field: string, v: Tri) => update((p) => ({ ...p, supplier: { ...p.supplier, answers: { ...p.supplier.answers, [field]: v } } }));
  const problems = tried ? supplierProblems(profile) : [];
  const errorOf = (id: string) => problems.find((x) => x.id === id)?.text;
  const shown = (h: Holding) => !h.esOnly || es;

  const save = () => {
    const found = supplierProblems(profile);
    setTried(true);
    if (found.length > 0) { setFocusSummary((n) => n + 1); return; }
    update((p) => savedSupplier(p));
    router.push('/readiness/results');
  };

  const holding = (h: Holding) => {
    const on = holds(profile, h);
    const month = s.expiry[h.key] ?? '';
    const isCert = CERTIFICATES.includes(h);
    return (
      <div key={h.key} className="flex flex-col">
        <Choice id={`q-${h.code ?? h.key}`} label={h.label} checked={on} onChange={(e) => update((p) => withHeld(p, h, e.target.checked))} />
        {on && isCert && (
          <TextInput id={`sp-expiry-${h.key}`} type="month" className="ml-8 max-w-56" label={`${h.label}: expiry month (optional)`} placeholder="YYYY-MM"
            value={month} onChange={(e) => setS('expiry', { ...s.expiry, [h.key]: e.target.value })}
            error={tried ? (monthProblem(month) ?? undefined) : undefined} />
        )}
      </div>
    );
  };

  return (
    <form noValidate className="flex flex-col gap-6" onSubmit={(e) => { e.preventDefault(); save(); }} aria-label="Supplier profile">
      {!stored && (
        <p role="alert" className="m-0 rounded-md bg-surface-inset p-3 text-small">
          Your browser would not save the answers (private window or blocked storage). They are kept while this page is open and are lost when you leave it.
        </p>
      )}
      <div ref={summaryRef} tabIndex={-1} role={problems.length > 0 ? 'alert' : undefined} className={cn(problems.length === 0 && 'hidden')}>
        {problems.length > 0 && (
          <div className="flex flex-col gap-2 rounded-md border-strong border-alert bg-surface p-4">
            <p className="m-0 font-bold text-alert">{problems.length === 1 ? 'One answer needs a change before saving' : `${problems.length} answers need a change before saving`}</p>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {problems.map((x) => (
                <li key={x.id}><a href={`#${x.id}`} className="inline-flex min-h-11 items-center font-semibold"
                  onClick={(e) => { e.preventDefault(); document.getElementById(x.id)?.focus(); }}>{x.text}</a></li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <Part title="Your company" id="sp-company">
        <Select id="sp-country" className="max-w-form" label="Country where your company is established" placeholder="Choose a country" options={COUNTRY_OPTIONS}
          value={profile.country} aria-required="true" error={errorOf('sp-country')}
          onChange={(e) => update((p) => ({ ...p, country: e.target.value, supplier: { ...p.supplier, region: '' } }))} />
        {es
          ? <Select className="max-w-form" label="Region (optional)" placeholder="Choose a region" options={ES_REGIONS} value={s.region} onChange={(e) => setS('region', e.target.value)} />
          : <TextInput className="max-w-form" label="Region (optional)" maxLength={60} value={s.region} onChange={(e) => setS('region', e.target.value)} />}
        <Select className="max-w-form" label="Size of the company (optional)" hint="Kept for your own summary. No rule reads it." placeholder="Choose" options={SIZE_OPTIONS}
          value={profile.sizeClass} onChange={(e) => update((p) => ({ ...p, sizeClass: e.target.value as Profile['sizeClass'] }))} />
        <TextInput id="sp-nace" className="max-w-form" label="NACE code of your main activity (optional)" hint="For example 25.50 (forging, pressing, stamping and roll-forming of metal). No rule reads it."
          maxLength={12} value={s.nace} onChange={(e) => setS('nace', e.target.value)} error={tried ? (naceProblem(s.nace) ?? undefined) : undefined} />
        <Radios legend="Does a foreign investor own or control part of your company, directly or indirectly?" name="foreign_capital" value={s.foreignOwner}
          hint="A rule of the Spanish Ministry of Defence route reads this answer; your results show it with its source." options={[...YES_NO_UNSURE]}
          // no foreign shareholder at all also answers the wizard's "controlled from outside the EU?" with "no", when that was empty
          onChange={(v) => update((p) => ({ ...p, control: v === 'no' && p.control === '' ? 'no' : p.control, supplier: { ...p.supplier, foreignOwner: v } }))} />
        {s.foreignOwner === 'yes' && (
          <Select className="max-w-form" label="Country of that investor (optional)" hint="Kept for your own summary. No rule reads it." placeholder="Choose a country"
            options={COUNTRY_OPTIONS} value={s.foreignCountry} onChange={(e) => setS('foreignCountry', e.target.value)} />
        )}
      </Part>

      <Part title="What you make" id="sp-make">
        <CpvPicker codes={s.cpv} onChange={(codes) => setS('cpv', codes)} error={tried ? (cpvProblem(s.cpv) ?? undefined) : undefined} />
        <Fieldset id="q-processes" legend="Processes you run (optional)" hint="Kept for your own summary. No rule reads them.">
          {PROCESSES.map((x) => (
            <Choice key={x.value} label={x.label} checked={s.processes.includes(x.value)}
              onChange={(e) => setS('processes', e.target.checked ? [...s.processes, x.value] : s.processes.filter((v) => v !== x.value))} />
          ))}
        </Fieldset>
      </Part>

      <Part title="Certificates and registrations" id="sp-certs">
        <Fieldset id="q-certificates" legend="Certificates you hold" hint="Tick what you hold now. These are the same answers as step 4 of the readiness check; an unticked one counts as not held.">
          {CERTIFICATES.filter(shown).map(holding)}
        </Fieldset>
        <Fieldset id="q-registrations" legend="Registrations you hold" hint="An unticked one counts as not held.">
          {REGISTRATIONS.filter(shown).map(holding)}
        </Fieldset>
      </Part>

      <Part title="Origin and classified work" id="sp-origin">
        <Radios legend="Does your product contain components, technology or software of US origin?" name="us_components" value={s.usComponents}
          hint="This check has no verified rule on US-origin parts. Unless you answer no, your results say that a specialist is needed."
          options={[...YES_NO_UNSURE]} onChange={(v) => setS('usComponents', v)} />
        <Radios legend="Will you need access to classified information in a contract?" name="classified" value={profile.classified}
          hint="The same answer as step 5 of the readiness check." options={[...YES_NO_UNSURE]} onChange={(v) => update((p) => ({ ...p, classified: v }))} />
      </Part>

      {es && (
        <Part title="Questions of the Spanish defence supplier route (optional)" id="sp-spain">
          <p className="m-0 max-w-prose text-small text-ink-muted">
            The rules of the Ministry of Defence route read these answers. Leave a question empty, or answer “I am not sure”, and the rule stays open with its question on your results.
          </p>
          {ES_QUESTIONS.filter((q) => !q.when || q.when(profile)).map((q) => (
            <Radios key={q.field} legend={q.label} name={q.field} value={s.answers[q.field] ?? ''} options={[...YES_NO_UNSURE]} onChange={(v) => answer(q.field, v)} />
          ))}
        </Part>
      )}

      <div className="flex flex-col gap-3">
        <p className="m-0 max-w-prose text-small text-ink-muted">
          Saved in this browser as you go. The CPV codes, processes, region, NACE code and investor country never leave it; the results page sends only the answers the rules read.
        </p>
        <div><Button type="submit" iconRight={ArrowRight}>Save and see my results</Button></div>
      </div>
    </form>
  );
}

/**
 * Choosing 5 to 15 CPV codes from our dictionary: a search box (a code prefix, a product word of the curated list, or words of the official
 * titles, whole words only) and the codes chosen, each with a button to remove it. The count of matches is announced.
 */
function CpvPicker({ codes, onChange, error }: { codes: string[]; onChange: (codes: string[]) => void; error?: string }) {
  const [query, setQuery] = useState('');
  const found = query.trim() ? cpvSearch(query) : [];
  const full = codes.length >= CPV_MAX;
  return (
    <Fieldset id="q-cpv" legend={`CPV codes of what you make (choose 5 to ${CPV_MAX})`} error={error}
      hint="Search by a word of the product (“vehicles”, “cable”, “parts”) or by the first digits of a code. The codes and titles are those of the official CPV vocabulary.">
      <TextInput id="sp-cpv-search" search className="mt-2 max-w-form" label="Search the CPV codes" value={query} onChange={(e) => setQuery(e.target.value)}
        aria-invalid={error ? true : undefined} aria-describedby={error ? 'q-cpv-error' : undefined} autoComplete="off" />
      <p role="status" className="m-0 text-small text-ink-muted">
        {query.trim() === '' ? '' : found.length === 0 ? 'No code matches. Try another word, or the first digits of a code.' : `${found.length === 20 ? 'The first 20' : found.length} ${found.length === 1 ? 'code matches' : 'codes match'}.`}
        {full ? ` You have chosen ${CPV_MAX}, the most a profile holds.` : ''}
      </p>
      {found.length > 0 && (
        <div className="flex max-h-96 flex-col overflow-y-auto">
          {found.map((c) => (
            <Choice key={c.code} label={<><span className="font-mono">{c.code}</span> {c.title}</>} checked={codes.includes(c.code)} disabled={full && !codes.includes(c.code)}
              onChange={(e) => onChange(e.target.checked ? [...codes, c.code] : codes.filter((x) => x !== c.code))} />
          ))}
        </div>
      )}
      <p className="m-0 mt-3 text-label text-ink">Your codes ({codes.length} of {CPV_MAX})</p>
      {codes.length === 0
        ? <p className="m-0 text-small text-ink-muted">None chosen yet.</p>
        : (
          <ul className="m-0 flex list-none flex-col p-0" aria-label="Your CPV codes">
            {codes.map((code) => (
              <li key={code} className="flex min-h-11 items-center justify-between gap-2 border-b border-line">
                <span className="min-w-0 text-small"><span className="font-mono">{code}</span> {cpvDictionaryTitle(code) ?? ''}</span>
                <button type="button" onClick={() => onChange(codes.filter((x) => x !== code))} aria-label={`Remove ${code}`}
                  className="inline-flex size-11 shrink-0 items-center justify-center border-0 bg-transparent p-0 text-ink"><X size={18} aria-hidden="true" /></button>
              </li>
            ))}
          </ul>
        )}
    </Fieldset>
  );
}
