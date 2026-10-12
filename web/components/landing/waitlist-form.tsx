'use client';

import { useActionState } from 'react';
import { CircleAlert, Clock } from 'lucide-react';
import { joinWaitlist, type WaitlistState } from '@/app/(public)/actions';
import { EMAIL_MAX_LENGTH, CERTIFICATIONS, SECTORS, STAFF_SIZES } from '@/lib/intake';
import { AUDIENCE_COUNTRIES, countryName } from '@/lib/taxonomy';
import { Button } from '../dg/button';
import { Choice, Fieldset, Select, TextInput } from '../dg/form';
import { Icon } from '../dg/icon';

const initial: WaitlistState = { status: 'idle' };

function FieldError({ children }: { children: string }) {
  return <span className="flex items-center gap-1 text-small text-alert"><Icon icon={CircleAlert} size="inline" />{children}</span>;
}

export function WaitlistForm() {
  const [state, action, pending] = useActionState(joinWaitlist, initial);
  if (state.status === 'closed') {
    return (
      <div role="status" className="flex flex-col items-start gap-3 rounded-lg bg-surface p-6">
        <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={Clock} /></span>
        <h3 className="m-0 text-h3">Sign-ups are not open yet</h3>
        <p className="m-0 text-body text-ink-muted">{state.message ?? 'Sign-ups are not open yet. Nothing you entered was stored or sent.'}</p>
        <Button href="/funding" variant="secondary">Browse funding calls</Button>
      </div>
    );
  }
  const e = state.errors ?? {};
  return (
    <form action={action} noValidate className="flex flex-col gap-5 rounded-lg bg-surface p-5 sm:p-6">
      <p className="m-0 text-small text-ink-muted">Sign-ups are not open yet. Nothing you enter here is stored or sent.</p>
      {e.form && <p role="alert" className="m-0 flex items-center gap-1 text-small text-alert"><Icon icon={CircleAlert} size="inline" />{e.form}</p>}
      <TextInput name="email" type="email" autoComplete="email" maxLength={EMAIL_MAX_LENGTH} label="Work email" required error={e.email} />
      <div className="grid gap-5 sm:grid-cols-2">
        <Select name="country" label="Company based in" placeholder="Choose country" required error={e.country}
          options={AUDIENCE_COUNTRIES.map((c) => ({ value: c, label: `${c} ${countryName(c)}` }))} />
        <Select name="sector" label="Sector" placeholder="Choose sector" error={e.sector} options={SECTORS.map((s) => ({ value: s, label: s }))} />
      </div>
      <Fieldset legend="Staff size">
        <div className="flex flex-wrap gap-x-6">
          {STAFF_SIZES.map((s) => <Choice key={s} type="radio" name="staff" value={s} label={<span className="font-mono">{s}</span>} />)}
        </div>
        {e.staff && <FieldError>{e.staff}</FieldError>}
      </Fieldset>
      <Fieldset legend="Certifications held">
        <div className="grid sm:grid-cols-2">
          {CERTIFICATIONS.map((c) => <Choice key={c} name="certifications" value={c} label={c} />)}
        </div>
        {e.certifications && <FieldError>{e.certifications}</FieldError>}
      </Fieldset>
      <div>
        <Button type="submit" disabled={pending}>{pending ? 'Checking' : 'Join the waitlist'}</Button>
      </div>
    </form>
  );
}
