'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { CERTIFICATES, REGISTRATIONS, holds } from '@/lib/profile';
import { L, type SellReport } from '@/lib/sell-report';
import type { SellForm } from '@/lib/sell-report-api';
import { Button } from '@/components/dg/button';
import { Choice, Fieldset, Select, TextInput } from '@/components/dg/form';
import { PrintButton } from '@/components/dg/print-button';
import { CARD_PADDING, CARD_SURFACE } from '@/components/dg/card';
import { CpvPicker } from '@/components/readiness/supplier';
import { COUNTRY_OPTIONS, EXPORT_OPTIONS, Radios, YES_NO_UNSURE } from '@/components/readiness/wizard';
import { useProfile } from '@/components/readiness/use-readiness';
import { makeReport, forgetForm, type MakeResult } from '@/app/(public)/reports/who-to-sell-to/actions';
import { SellReportView } from './report';

type Tri = '' | 'yes' | 'no' | 'unsure';
interface State { name: string; country: string; cpv: string[]; nace: string; size: '' | 'sme' | 'large'; held: string[]; classified: Tri; exports: string; usComponents: Tri; consent: boolean }
const EMPTY: State = { name: '', country: '', cpv: [], nace: '', size: '', held: [], classified: '', exports: '', usComponents: '', consent: false };

function fromKept(k: SellForm | null): State | null {
  if (!k) return null;
  return { ...EMPTY, name: k.name ?? '', country: k.country ?? '', cpv: k.cpv ?? [], nace: k.nace ?? '', size: (k.size as State['size']) ?? '',
    held: k.held ?? [], classified: (k.classified as Tri) ?? '', exports: k.exports ?? '', usComponents: (k.usComponents as Tri) ?? '', consent: true };
}

function refusal(r: Extract<MakeResult, { ok: false }>): string {
  if (r.error === 'report_quota') return `${(r.message ?? 'No supplier reports left').replace(/^./, (c) => c.toUpperCase())}.`;
  if (r.error === 'plan_required') return 'The supplier report comes with a paid plan (Pro, Team or Consultant). See Billing in your account.';
  if (r.status === 401) return 'Your session has ended. Sign in again, then generate the report.';
  if (r.status === 422) return 'An answer could not be read: check the country and the CPV codes.';
  if (r.status === 404) return 'Supplier reports are not open yet.';
  return 'The report could not be made just now. Try again in a moment.';
}

/**
 * WP-162, mode B: a civilian maker describes itself (CPV codes from the CPV dictionary and the product-word map, never a model) and gets
 * its report. The answers are kept in this page's memory only; the server keeps them only when the consent box is ticked. Prefilled from
 * the form the account chose to keep, else from the supplier profile saved in this browser.
 */
export function SellReportForm({ kept }: { kept: SellForm | null }) {
  const [s, setS] = useState<State>(() => fromKept(kept) ?? EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<SellReport | null>(null);
  const top = useRef<HTMLDivElement>(null);
  const { profile, ready } = useProfile();
  const filled = useRef(kept !== null);
  useEffect(() => {
    if (filled.current || !ready || !profile?.country) return;
    filled.current = true;
    const held = [...CERTIFICATES, ...REGISTRATIONS].filter((h) => holds(profile, h)).map((h) => h.key);
    setS((x) => ({ ...x, name: profile.name ?? '', country: profile.country, cpv: profile.supplier.cpv.slice(0, 15), nace: profile.supplier.nace, held,
      classified: (profile.classified as Tri) || '', usComponents: (profile.supplier.usComponents as Tri) || '', exports: profile.exportIntent || '' }));
  }, [ready, profile]);
  const set = <K extends keyof State>(k: K, v: State[K]) => setS((x) => ({ ...x, [k]: v }));

  const submit = async () => {
    if (!s.country) { setError('Choose the country where your company is established.'); return; }
    if (s.cpv.length === 0) { setError('Choose at least one CPV code of what you make.'); return; }
    setBusy(true); setError(null);
    const r = await makeReport({ ...s, name: s.name.trim() || undefined, nace: s.nace.trim() || undefined }).catch(() => null);
    setBusy(false);
    if (r?.ok) { setReport(r.report); window.scrollTo({ top: 0 }); return; }
    setError(r ? refusal(r) : 'The report could not be made just now. Try again in a moment.');
    top.current?.focus();
  };

  if (report) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3 print:hidden">
          <PrintButton>{L.printButton}</PrintButton>
          <Button variant="secondary" onClick={() => setReport(null)}>Change the answers</Button>
          {report.quota && report.quota.limit !== null && (
            <p className="m-0 text-small text-ink-muted" data-sr-quota>{`${report.quota.used} of ${report.quota.limit} supplier reports used this ${report.quota.per}.`}</p>
          )}
        </div>
        <SellReportView r={report} />
      </div>
    );
  }

  const box = (h: { key: string; label: string }) => (
    <Choice key={h.key} label={h.label} checked={s.held.includes(h.key)}
      onChange={(e) => set('held', e.target.checked ? [...s.held, h.key] : s.held.filter((x) => x !== h.key))} />
  );
  return (
    <form noValidate aria-label="Your company" className={`flex flex-col gap-5 ${CARD_SURFACE} ${CARD_PADDING}`} onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      <div ref={top} tabIndex={-1} role={error ? 'alert' : undefined}>{error && <p className="m-0 font-semibold text-alert" data-sr-error>{error}</p>}</div>
      <TextInput label="Company name (optional, printed on the cover)" maxLength={120} value={s.name} onChange={(e) => set('name', e.target.value)} />
      <Select className="max-w-form" label="Country where your company is established" placeholder="Choose a country" options={COUNTRY_OPTIONS}
        value={s.country} aria-required="true" onChange={(e) => set('country', e.target.value)} />
      <CpvPicker codes={s.cpv} onChange={(codes) => set('cpv', codes)} />
      <TextInput className="max-w-form" label="NACE code of your main activity (optional)" maxLength={12} value={s.nace} onChange={(e) => set('nace', e.target.value)} />
      <Radios legend="Size of your company" name="size" value={s.size} hint="Small or medium: fewer than 250 staff and a turnover of at most EUR 50 million (Commission Recommendation 2003/361/EC)."
        options={[{ value: 'sme', label: 'Small or medium' }, { value: 'large', label: 'Large' }]} onChange={(v) => set('size', v)} />
      <Fieldset id="q-held" legend="Certificates and registrations you hold" hint="An unticked one counts as not held.">
        {[...CERTIFICATES, ...REGISTRATIONS].filter((h) => !h.esOnly || s.country === 'ES').map(box)}
      </Fieldset>
      <Radios legend="Do you export, or plan to export, your product?" name="exports" value={s.exports as never} options={[...EXPORT_OPTIONS]} onChange={(v) => set('exports', v)} />
      <Radios legend="Will you need access to classified information in a contract?" name="classified" value={s.classified} options={[...YES_NO_UNSURE]} onChange={(v) => set('classified', v)} />
      <Radios legend="Does your product contain US-origin parts, software or technology?" name="us" value={s.usComponents} options={[...YES_NO_UNSURE]} onChange={(v) => set('usComponents', v)} />
      <div className="flex flex-col gap-2 rounded-md border border-line p-4" data-sr-consent>
        <Choice label="Keep these answers on DefenceGate's server for my next report" checked={s.consent} onChange={(e) => set('consent', e.target.checked)}
          hint="Unticked (the default), the answers are used for this report only: sent to make it, kept in no log and no database, and lost when you leave this page. Ticked, they are kept with your account until you delete them here or delete the account." />
        {kept && (
          <div><Button type="button" variant="secondary" onClick={() => { void forgetForm().then(() => { set('consent', false); }); }}>Delete the answers kept on the server</Button></div>
        )}
      </div>
      <div><Button type="submit" iconRight={ArrowRight} disabled={busy}>{busy ? 'Making the report…' : 'Make the report'}</Button></div>
    </form>
  );
}
