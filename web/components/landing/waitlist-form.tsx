'use client';

import { useActionState } from 'react';
import { CircleCheck } from 'lucide-react';
import { joinWaitlist, type WaitlistState } from '@/app/(public)/actions';
import { AUDIENCE_COUNTRIES, countryName } from '@/lib/taxonomy';
import { Button } from '../dg/button';
import { Choice, Fieldset, Select, TextInput } from '../dg/form';
import { Icon } from '../dg/icon';
import { CircleAlert } from 'lucide-react';

export const SECTORS = ['Metalworking and machining', 'Electronics and electrical', 'Plastics and composites', 'Textiles', 'Chemicals and materials', 'Software and IT', 'Logistics and services', 'Other manufacturing'];
export const STAFF_SIZES = ['20–49', '50–249', '250–500'];
export const CERTIFICATIONS = ['ISO 9001', 'EN 9100 / AS9100', 'AQAP 2110', 'ISO 27001', 'Facility security clearance', 'None yet'];

const initial: WaitlistState = { status: 'idle' };

export function WaitlistForm() {
  const [state, action, pending] = useActionState(joinWaitlist, initial);
  if (state.status === 'success') {
    return (
      <div role="status" className="flex flex-col items-start gap-3 rounded-lg bg-surface p-6">
        <span className="flex size-11 items-center justify-center rounded-pill bg-open-bg text-open-fg"><Icon icon={CircleCheck} /></span>
        <h3 className="m-0 text-h3">Check your inbox</h3>
        <p className="m-0 text-body text-ink-muted">We sent a confirmation link. Your place is saved once you click it.</p>
      </div>
    );
  }
  const e = state.errors ?? {};
  return (
    <form action={action} noValidate className="flex flex-col gap-5 rounded-lg bg-surface p-5 sm:p-6">
      <TextInput name="email" type="email" autoComplete="email" label="Work email" required error={e.email} />
      <div className="grid gap-5 sm:grid-cols-2">
        <Select name="country" label="Company based in" placeholder="Choose country" required error={e.country}
          options={AUDIENCE_COUNTRIES.map((c) => ({ value: c, label: `${c} ${countryName(c)}` }))} />
        <Select name="sector" label="Sector" placeholder="Choose sector" options={SECTORS.map((s) => ({ value: s, label: s }))} />
      </div>
      <Fieldset legend="Staff size">
        <div className="flex flex-wrap gap-x-6">
          {STAFF_SIZES.map((s) => <Choice key={s} type="radio" name="staff" value={s} label={<span className="font-mono">{s}</span>} />)}
        </div>
        {e.staff && <span className="flex items-center gap-1 text-small text-alert"><Icon icon={CircleAlert} size="inline" />{e.staff}</span>}
      </Fieldset>
      <Fieldset legend="Certifications held">
        <div className="grid sm:grid-cols-2">
          {CERTIFICATIONS.map((c) => <Choice key={c} name="certifications" value={c} label={c} />)}
        </div>
      </Fieldset>
      <div className="flex flex-col">
        <Choice name="consent" label="Email me when DefenceGate opens. I can unsubscribe at any time." />
        {e.consent && <span className="flex items-center gap-1 text-small text-alert"><Icon icon={CircleAlert} size="inline" />{e.consent}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" disabled={pending}>{pending ? 'Sending' : 'Join the waitlist'}</Button>
        <a href="/privacy" className="text-small font-bold">How we use this data</a>
      </div>
    </form>
  );
}
