'use client';

import { useActionState } from 'react';
import Link from 'next/link';
import { CircleAlert, MailCheck } from 'lucide-react';
import { requestSignIn, type SignInState } from '@/app/(public)/signin/actions';
import { Button } from '../dg/button';
import { TextInput } from '../dg/form';
import { Icon } from '../dg/icon';

const initial: SignInState = { status: 'idle' };

const MESSAGE: Partial<Record<SignInState['status'], string>> = {
  invalid: 'That does not look like an e-mail address.',
  rate_limited: 'Too many requests. Try again later.',
  unavailable: 'Sign-in is temporarily unavailable. Try again in a few minutes.',
};

export function SignInForm() {
  const [state, action, pending] = useActionState(requestSignIn, initial);

  if (state.status === 'sent') {
    return (
      <div role="status" className="flex max-w-[860px] flex-col items-start gap-3 rounded-lg bg-surface p-6">
        <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={MailCheck} /></span>
        <h2 className="m-0 text-h3">Check your mail</h2>
        <p className="m-0 text-body text-ink-muted">
          If the address can receive mail, a sign-in link is on its way. Open it in this browser. It works once and expires in 15 minutes.
        </p>
      </div>
    );
  }

  const message = MESSAGE[state.status];
  return (
    <form action={action} noValidate className="flex max-w-[560px] flex-col gap-5 rounded-lg bg-surface p-5 sm:p-6">
      <TextInput
        name="email" type="email" autoComplete="email" inputMode="email" maxLength={254} required
        label="E-mail address" hint="We send one sign-in link. There is no password."
        defaultValue={state.email ?? ''} key={state.email ?? 'new'}
        error={state.status === 'invalid' ? message : undefined}
      />
      {message && state.status !== 'invalid' && (
        <p role="alert" className="m-0 flex items-center gap-1 text-small text-alert"><Icon icon={CircleAlert} size="inline" />{message}</p>
      )}
      <p className="m-0 text-small text-ink-muted">
        By signing in you confirm that you act for a trade, business or profession and accept the <Link href="/terms" className="font-semibold">terms of use</Link>.
        How we handle your e-mail address is in the <Link href="/privacy" className="font-semibold">privacy notice</Link>.
      </p>
      <div><Button type="submit" disabled={pending}>{pending ? 'Sending' : 'Send sign-in link'}</Button></div>
    </form>
  );
}
