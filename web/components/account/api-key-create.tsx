'use client';

import { useActionState, useState } from 'react';
import Link from 'next/link';
import { CircleAlert } from 'lucide-react';
import { newApiKey, type KeyState } from '@/app/(app)/app/actions';
import { Button, buttonVariants } from '../dg/button';
import { Choice, Fieldset, TextInput } from '../dg/form';
import { Icon } from '../dg/icon';

const initial: KeyState = { status: 'idle' };
const ERRORS: Partial<Record<KeyState['status'], string>> = {
  wrong_password: 'The password is wrong. No key was made.',
  too_many: 'This account has the most keys it may hold. Revoke one first.',
  closed: 'API keys are not issued yet.',
  invalid: 'Give the key a name and at least one scope.',
  rate_limited: 'Too many attempts. Wait a little and try again.',
  error: 'That did not work. Try again.',
};

/** WP-153: a new key, shown once in the answer (useActionState keeps it on this page only; the site stores nothing). */
export function ApiKeyCreate() {
  const [state, create, creating] = useActionState(newApiKey, initial);
  // 'Done' leaves the page for itself: a client navigation keeps this component and its state, so the key is put away here
  const [putAway, setPutAway] = useState<string | null>(null);
  if (state.status === 'created' && state.key && state.key !== putAway) {
    return (
      <div role="status" className="flex max-w-form flex-col gap-3" data-new-key>
        <p className="m-0 text-body font-semibold">Key “{state.name}” is made.</p>
        <p className="m-0 text-body text-ink-muted">Copy it now: it is shown only this once and cannot be shown again. Send it as <code className="font-mono text-mono">Authorization: Bearer &lt;key&gt;</code>.</p>
        <p className="m-0 break-all rounded-md bg-surface-inset px-3 py-2 font-mono text-mono" aria-label="Your new key">{state.key}</p>
        <div><Link href="/app/keys" className={buttonVariants({ variant: 'secondary' })} onClick={() => setPutAway(state.key ?? null)}>Done</Link></div>
      </div>
    );
  }
  const text = ERRORS[state.status];
  const kept = state.status === 'created' ? '' : state.name ?? '';     // a refused name comes back, a made key's does not
  return (
    <form action={create} className="flex max-w-form flex-col gap-4">
      <TextInput key={`${state.status}:${kept}`} name="name" defaultValue={kept} required maxLength={60} label="Name" hint="What the key is for, so you know which one to revoke." />
      <Fieldset legend="Scopes">
        <Choice name="scopes" value="tenders" defaultChecked label="Notices" hint="/v1/opportunities and one notice" />
        <Choice name="scopes" value="archive" defaultChecked label="Archive" hint="the versions of a notice" />
      </Fieldset>
      <TextInput name="password" type="password" autoComplete="current-password" maxLength={1024} required label="Your password" />
      {text && <p role="alert" className="m-0 flex items-center gap-1 text-small text-alert"><Icon icon={CircleAlert} size="inline" />{text}</p>}
      <div><Button type="submit" disabled={creating}>{creating ? 'Making the key' : 'Make a key'}</Button></div>
    </form>
  );
}
