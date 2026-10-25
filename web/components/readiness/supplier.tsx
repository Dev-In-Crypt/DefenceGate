'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, X } from 'lucide-react';
import { CODE_SETS, cpvDictionaryTitle, cpvSearch, productNote, setUpdate, type CodeSet } from '@/lib/cpv';
import {
  CERTIFICATES, CPV_MAX, CPV_MIN, DE_QUESTIONS, DUAL_USE_QUESTION, ES_CLEARANCES, EXPORT_HOLDING, ES_QUESTIONS, EU_QUESTION, PROCESSES, REGISTRATIONS, SERVICE_PROCESSES, clearanceAnswer,
  cpvProblem, holds, isEu, monthProblem, naceProblem, pctProblem, providesServices, savedSupplier, supplierProblems, withClearance, withHeld,
  type Answer, type EsQuestion, type Holding, type Profile, type Supplier,
} from '@/lib/profile';
import { cn } from '@/lib/utils';
import { CARD_PADDING, CARD_SURFACE } from '@/components/dg/card';
import { Button } from '@/components/dg/button';
import { Choice, Fieldset, Select, TextInput } from '@/components/dg/form';
import { COUNTRY_OPTIONS, ComponentOriginQuestions, ComponentShareQuestion, ControlQuestion, EXPORT_OPTIONS, InvestorQuestion, LEGAL_FORM_OPTIONS, MANAGEMENT_OPTIONS, Radios, SAFE_ROLE_OPTIONS, SizeQuestions, YES_NO_UNSURE } from './wizard';
import { useCpvVocabulary, useProfile } from './use-readiness';
import { SavedAnswersLoading } from './loading';

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
export function SupplierForm({ offer = null }: { offer?: 'services' | 'products' | null } = {}) {
  const router = useRouter();
  const { profile, ready, update, stored } = useProfile();
  const [tried, setTried] = useState(false);
  const summaryRef = useRef<HTMLDivElement>(null);
  const [focusSummary, setFocusSummary] = useState(0);
  useEffect(() => { if (focusSummary) summaryRef.current?.focus(); }, [focusSummary]);
  // WP-97: "/check" opens this page with the answer given ("?offer=services"), unless one is stored already
  useEffect(() => {
    if (!ready || !offer || !profile || profile.offering) return;
    update((p) => ({ ...p, offering: offer === 'services' ? 'software_services' : 'products' }));
  }, [ready, offer, profile, update]);

  if (!ready || profile === null) return <SavedAnswersLoading />;
  const s = profile.supplier;
  const es = profile.country === 'ES';
  const setS = <K extends keyof Supplier>(key: K, value: Supplier[K]) => update((p) => ({ ...p, supplier: { ...p.supplier, [key]: value } }));
  const de = profile.country === 'DE';
  const answer = (field: string, v: Answer) => update((p) => ({ ...p, supplier: { ...p.supplier, answers: { ...p.supplier.answers, [field]: v } } }));
  const question = (q: EsQuestion, hint?: string) => (
    <Radios key={q.field} legend={q.label} name={q.field} value={s.answers[q.field] ?? ''} hint={hint}
      options={q.options ? [...q.options] : [...YES_NO_UNSURE]} onChange={(v) => answer(q.field, v)} />
  );
  const shownQ = (q: EsQuestion) => !q.when || q.when(profile);
  const problems = tried ? supplierProblems(profile) : [];
  const errorOf = (id: string) => problems.find((x) => x.id === id)?.text;
  const shown = (h: Holding) => !h.esOnly || es;
  const services = providesServices(profile);

  const save = () => {
    const found = supplierProblems(profile);
    setTried(true);
    if (found.length > 0) { setFocusSummary((n) => n + 1); return; }
    update((p) => savedSupplier(p));
    // WP-97: the results say "Supplier report" and lead back here when they are reached from this page
    router.push('/readiness/results?from=supplier');
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
        <SizeQuestions profile={profile} update={update} />
        <TextInput id="sp-nace" className="max-w-form" label="NACE code of your main activity (optional)" hint="For example 25.50 (forging, pressing, stamping and roll-forming of metal). No rule reads it."
          maxLength={12} value={s.nace} onChange={(e) => setS('nace', e.target.value)} error={tried ? (naceProblem(s.nace) ?? undefined) : undefined} />
        <Radios legend="Does a foreign investor own or control part of your company, directly or indirectly?" name="foreign_capital" value={s.foreignOwner}
          hint={es ? 'A rule of the Spanish Ministry of Defence route reads this answer; your results show it with its source.' : 'No rule of this check reads it for a company outside Spain; it is kept for your own summary.'}
          options={[...YES_NO_UNSURE]}
          // no foreign shareholder at all also answers the wizard's "controlled from outside the EU?" with "no", when that was empty
          onChange={(v) => update((p) => ({ ...p, control: v === 'no' && p.control === '' ? 'no' : p.control, supplier: { ...p.supplier, foreignOwner: v } }))} />
        {s.foreignOwner === 'yes' && (
          <Select className="max-w-form" label="Country of that investor (optional)" hint="Kept for your own summary. No rule reads it." placeholder="Choose a country"
            options={COUNTRY_OPTIONS} value={s.foreignCountry} onChange={(e) => setS('foreignCountry', e.target.value)} />
        )}
      </Part>

      <Part title={services ? 'What you provide' : 'What you make'} id="sp-make">
        {/* WP-97: products or services; the same answer as the readiness check's "What do you offer?" */}
        <Radios legend="Do you sell products or services?" name="offering" value={profile.offering}
          hint="Services: logistics, transport, fuel, facility services, catering, maintenance and repair, training or IT services. The processes and the suggested codes below follow the answer."
          options={[{ value: 'products', label: 'We make products: equipment, parts or materials' }, { value: 'software_services', label: 'We provide services' }]}
          onChange={(v) => update((p) => ({ ...p, offering: v }))} />
        <CpvPicker codes={s.cpv} services={services} onChange={(codes) => setS('cpv', codes)} error={tried ? (cpvProblem(s.cpv) ?? undefined) : undefined} />
        <Fieldset id="q-processes" legend={services ? 'Services you provide (optional)' : 'Processes you run (optional)'} hint="Kept for your own summary. No rule reads them.">
          {(services ? SERVICE_PROCESSES : PROCESSES).map((x) => (
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
        {/* WP-73: a clearance is asked, never assumed "not held"; "I am not sure" leaves the rule open with its question */}
        {es && ES_CLEARANCES.filter((q) => q.when(profile)).map((q) => (
          <Radios key={q.code} legend={q.label} name={q.code} value={clearanceAnswer(profile, q.code)} options={[...YES_NO_UNSURE]}
            hint="The same answer as step 4 of the readiness check. If you are not sure, your results keep the question open."
            onChange={(v) => update((p) => withClearance(p, q.code, v))} />
        ))}
        {!es && isEu(profile.country) && (
          <Radios legend="Do you receive defence-related products from other EEA states?" name={EU_QUESTION} value={s.answers[EU_QUESTION] ?? ''}
            hint="A general rule on certified recipients reads this answer." options={[...YES_NO_UNSURE]} onChange={(v) => answer(EU_QUESTION, v)} />
        )}
      </Part>

      {/* WP-68: the export answer of step 5, the EU dual-use question and, for a German company, the German export list */}
      <Part title="Exports and export control" id="sp-export">
        <Radios legend="Do you export, or plan to export, your product?" name="export_intent" value={profile.exportIntent}
          hint="The same answer as step 5 of the readiness check. The export rules read it." options={[...EXPORT_OPTIONS]}
          onChange={(v) => update((p) => ({ ...p, exportIntent: v }))} />
        {shownQ(DUAL_USE_QUESTION)
          ? question(DUAL_USE_QUESTION, 'The EU rule on dual-use exports reads this answer when you export, or may export, outside the EU. If you are not sure, your results say that a classification settles it and that a specialist is needed; this check does not classify items.')
          : <p className="m-0 max-w-prose text-small text-ink-muted" data-dual-use-hidden>
              The question on the EU dual-use list (Annex I of Regulation (EU) 2021/821) is asked when you export, or may export, outside the EU, unless you said in step 3 of the readiness check that your main product is military or in neither regime.
            </p>}
        {de && shownQ(DE_QUESTIONS.find((q) => q.field === 'de_ausfuhrliste')!)
          && question(DE_QUESTIONS.find((q) => q.field === 'de_ausfuhrliste')!, 'The German rule on BAFA licences reads this answer. If you are not sure, your results say that a classification settles it.')}
        {EXPORT_HOLDING.when(profile) && (
          <Radios legend={EXPORT_HOLDING.label} name={EXPORT_HOLDING.code} value={clearanceAnswer(profile, EXPORT_HOLDING.code)} options={[...YES_NO_UNSURE]}
            hint="The same answer as step 4 of the readiness check. If you are not sure, your results keep the question open."
            onChange={(v) => update((p) => withClearance(p, EXPORT_HOLDING.code, v))} />
        )}
      </Part>

      {de && (
        <Part title="Questions of the German rules on classified contracts (optional)" id="sp-germany">
          <p className="m-0 max-w-prose text-small text-ink-muted">
            The German rules on the Geheimschutzbetreuung, the security officer and VS-NfD material read these answers; they apply to companies established in Germany. Leave a question empty, or answer “I am not sure”, and the rule stays open with its question on your results. The personnel security checks (Ü1 to Ü3) need no answer here: your results show that rule, with its source, once you say you need access to classified information.
          </p>
          {profile.classified === 'yes' || profile.classified === 'unsure'
            ? DE_QUESTIONS.filter((q) => q.field !== 'de_ausfuhrliste' && shownQ(q)).map((q) => question(q))
            : <p className="m-0 max-w-prose text-small text-ink-muted" data-germany-waiting>These questions appear once you answer “Yes” or “I am not sure” to access to classified information above.</p>}
        </Part>
      )}

      {es && (
        <Part title="Questions of the Spanish defence supplier route (optional)" id="sp-spain">
          <p className="m-0 max-w-prose text-small text-ink-muted">
            The rules of the Ministry of Defence route read these answers. Leave a question empty, or answer “I am not sure”, and the rule stays open with its question on your results.
          </p>
          {ES_QUESTIONS.filter(shownQ).map((q) => question(q))}
        </Part>
      )}

      {/* WP-89: the EU funding programmes' questions asked here, not by sending a supplier to the readiness check's steps */}
      <Part title="If you also want EU funding (optional)" id="sp-eu">
        <Radios legend="Do you also want EU funding: a grant of the European Defence Fund or EDIP, or a role in a SAFE-supported procurement?" name="eu_funding"
          value={s.euFunding} options={[...YES_NO_UNSURE]}
          hint="Supplying a ministry or a prime contractor needs none of it. Unless you answer yes, your results lead with the supply routes and your roadmap leaves out what only EU funding asks (the PIC)."
          onChange={(v) => setS('euFunding', v)} />
        {/* WP-107 (p04): the funding cards of the results list these as missing; say which they are and how to reach them, and ask them on "not sure" too */}
        {(s.euFunding === '' || s.euFunding === 'no') && (
          <p className="m-0 max-w-prose text-small text-ink-muted" data-eu-questions-hidden>
            The EU programmes read these answers too: the legal form, where the executive management is, control from outside the EU, the share of
            components from outside the EU, the origin of components, a Ukrainian partner, your role in SAFE, and whether you hold a PIC. Until they are
            answered, the EU funding cards of your results list them as missing. Answer yes or “I am not sure” above to see them here.
          </p>
        )}
        {(s.euFunding === 'yes' || s.euFunding === 'unsure') && (
          <>
            <p className="m-0 max-w-prose text-small text-ink-muted" data-eu-questions>
              The questions the EU programmes read, the same answers as the readiness check&rsquo;s. Leave one empty if you do not know; its rule then stays open with its question.
            </p>
            <Radios legend="What is the legal form of your organisation?" name="legal_form" value={profile.legalForm} options={[...LEGAL_FORM_OPTIONS]}
              onChange={(v) => update((p) => ({ ...p, legalForm: v }))} />
            <Radios legend="Where are your company's executive management structures?" name="management" value={profile.management} options={[...MANAGEMENT_OPTIONS]}
              hint="The place from which the company is actually run." onChange={(v) => update((p) => ({ ...p, management: v }))} />
            {profile.management === 'other' && (
              <Select className="max-w-form" label="Country of the executive management" placeholder="Choose a country" options={COUNTRY_OPTIONS}
                value={profile.managementCountry} onChange={(e) => update((p) => ({ ...p, managementCountry: e.target.value }))} />
            )}
            <ControlQuestion profile={profile} update={update} hint="Think of the ultimate owners, not only the first shareholder." />
            <InvestorQuestion profile={profile} update={update} />
            <ComponentShareQuestion profile={profile} update={update} />
            <Radios legend="Does any component come from a third country that contravenes the security and defence interests of the Union and its Member States?" name="restricted"
              value={profile.restricted} options={[...YES_NO_UNSURE]} onChange={(v) => update((p) => ({ ...p, restricted: v }))} />
            <ComponentOriginQuestions profile={profile} update={update} />
            {profile.country !== 'UA' && (
              <Radios legend="Does your planned consortium include a legal entity established in Ukraine, with its executive management structure there?" name="ua_partner"
                hint="Only the Ukraine Support Instrument asks for one." value={profile.uaPartner} options={[...YES_NO_UNSURE]}
                onChange={(v) => update((p) => ({ ...p, uaPartner: v }))} />
            )}
            <Radios legend="In a SAFE-supported procurement, what would your role be?" name="safe_role" value={profile.safeRole} options={[...SAFE_ROLE_OPTIONS]}
              onChange={(v) => update((p) => ({ ...p, safeRole: v }))} />
            <Radios legend="Do you hold a PIC (Participant Identification Code) of the EU Funding and Tenders Portal?" name="REQ-PIC"
              value={clearanceAnswer(profile, 'REQ-PIC')} options={[...YES_NO_UNSURE]}
              hint="A nine-digit code issued when an organisation registers on the portal; every EDF and EDIP application needs one."
              onChange={(v) => update((p) => withClearance(p, 'REQ-PIC', v))} />
          </>
        )}
      </Part>

      <div className="flex flex-col gap-3">
        <p className="m-0 max-w-prose text-small text-ink-muted">
          Saved in this browser as you go. The processes, region, NACE code and investor country never leave it; what the results page sends is listed
          under “What is kept and what is sent” at the top of this page. The server stores and logs neither request.
        </p>
        <div><Button type="submit" iconRight={ArrowRight}>Save and see my results</Button></div>
      </div>
    </form>
  );
}

/**
 * Choosing up to 15 CPV codes (5 to 15 recommended, none required: no rule reads them, WP-73) from the official CPV vocabulary, loaded on this
 * page only: a search box (a code prefix, a product word of the curated list, or words of the official titles, whole words only) and the
 * codes chosen, each with a button to remove it. The count of matches is announced.
 */
/** How many matches the picker lists (WP-73: the whole vocabulary matches more than the 20 of the selection did). */
const SHOWN = 50;

function CpvPicker({ codes, onChange, error, services = false }: { codes: string[]; onChange: (codes: string[]) => void; error?: string; services?: boolean }) {
  const [query, setQuery] = useState('');
  const vocab = useCpvVocabulary();
  const found = query.trim() ? cpvSearch(query, SHOWN, vocab ?? undefined) : [];
  const note = query.trim() ? productNote(query) : null;
  const title = (code: string) => vocab?.get(code) ?? cpvDictionaryTitle(code) ?? '';
  const full = codes.length >= CPV_MAX;
  // WP-89, WP-97: suggested sets (automotive, machining, ammunition, services), added to what is chosen (never past CPV_MAX), each code
  // removable below; a services company sees the services set first
  const sets = services ? [...CODE_SETS].sort((a, b) => Number(b.key === 'services') - Number(a.key === 'services')) : CODE_SETS;
  const [added, setAdded] = useState<{ set: string; n: number } | null>(null);
  const update = setUpdate(codes, CPV_MAX);
  const addSet = (set: CodeSet) => {
    const room = Math.max(0, CPV_MAX - codes.length);
    const take = set.codes.filter((c) => !codes.includes(c)).slice(0, room);
    onChange([...codes, ...take]);
    setAdded({ set: set.label, n: take.length });
  };
  return (
    // WP-107 (p06): a services company is asked for the codes of what it sells, with services as the examples
    <Fieldset id="q-cpv" legend={`CPV codes of what you ${services ? 'sell' : 'make'} (optional, up to ${CPV_MAX})`} error={error}
      hint={services
        ? `${CPV_MIN} to ${CPV_MAX} recommended for the demand map (who buys what you sell, on your results and in your report); no rule of the check reads them. Search by a word of the service (“warehousing”, “transport”, “catering”) or by the first digits of a code. The codes and titles are those of the official CPV 2008 vocabulary (Publications Office of the EU, CC BY 4.0).`
        : `${CPV_MIN} to ${CPV_MAX} recommended for the demand map (who buys what you make, on your results and in your report); no rule of the check reads them. Search by a word of the product (“castings”, “machined parts”, “fasteners”) or by the first digits of a code; products come before the machines that make them. The codes and titles are those of the official CPV 2008 vocabulary (Publications Office of the EU, CC BY 4.0).`}>
      {update && (
        // WP-110: a profile saved with an earlier version of a set is offered the current one; its own other codes stay
        <div className="mt-2 flex flex-col gap-1 rounded-md border border-line p-3" data-cpv-set-update={update.set.key}>
          <p className="m-0 text-body">
            {`Your codes hold an earlier version of “${update.set.label}”. The current set ${update.add.length ? `adds ${update.add.join(', ')}` : ''}${update.add.length && update.remove.length ? ' and ' : ''}${update.remove.length ? `drops ${update.remove.join(', ')}` : ''}; the other codes you chose stay.`}
          </p>
          <div><Button type="button" variant="secondary" onClick={() => { onChange(update.codes); setAdded({ set: update.set.label, n: update.add.length }); }}>Update to the current set</Button></div>
        </div>
      )}
      <div className="mt-2 flex flex-col gap-2" data-cpv-suggested>
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {sets.map((set) => (
            <li key={set.key} className="flex flex-col gap-0.5" data-cpv-set={set.key}>
              <div>
                <Button type="button" variant="secondary" className="whitespace-normal text-left" onClick={() => addSet(set)} disabled={set.codes.every((c) => codes.includes(c)) || full}>{`${set.label}: suggested codes`}</Button>
              </div>
              <p className="m-0 text-small text-ink-muted">{`Adds ${set.codes.length} codes: ${set.covers}.`}</p>
            </li>
          ))}
        </ul>
        <p role="status" className="m-0 text-small text-ink-muted">
          {added === null
            ? 'Remove afterwards the codes that do not fit what you do.'
            : added.n === 0 ? 'No code added: they are chosen already, or your list is full.' : `${added.n} ${added.n === 1 ? 'code' : 'codes'} of “${added.set}” added. Remove below the ones that do not fit what you do.`}
        </p>
      </div>
      <TextInput id="sp-cpv-search" search className="mt-2 max-w-form" label="Search the CPV codes" value={query} onChange={(e) => setQuery(e.target.value)}
        aria-invalid={error ? true : undefined} aria-describedby={error ? 'q-cpv-error' : undefined} autoComplete="off" />
      <p role="status" className="m-0 text-small text-ink-muted">
        {query.trim() === '' ? '' : found.length === 0 ? 'No code matches. Try another word, or the first digits of a code.' : `${found.length === SHOWN ? `The first ${SHOWN}` : found.length} ${found.length === 1 ? 'code matches' : 'codes match'}.${found.length === SHOWN ? ' Add a word or more digits to narrow the list.' : ''}`}
        {full ? ` You have chosen ${CPV_MAX}, the most a profile holds.` : ''}
      </p>
      {note && found.length > 0 && <p className="m-0 max-w-prose text-small" data-cpv-note>{note}</p>}
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
                <span className="min-w-0 text-small"><span className="font-mono">{code}</span> {title(code)}</span>
                <button type="button" onClick={() => onChange(codes.filter((x) => x !== code))} aria-label={`Remove ${code}`}
                  className="inline-flex size-11 shrink-0 items-center justify-center border-0 bg-transparent p-0 text-ink"><X size={18} aria-hidden="true" /></button>
              </li>
            ))}
          </ul>
        )}
    </Fieldset>
  );
}
