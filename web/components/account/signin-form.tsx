'use client';

import { useActionState } from 'react';
import Link from 'next/link';
import { CircleAlert, MailCheck } from 'lucide-react';
import {
  register, requestReset, setNewPassword, signIn, signInSecondStep, type AuthState,
} from '@/app/(public)/signin/actions';
import { Button } from '../dg/button';
import { Choice, TextInput } from '../dg/form';
import { Icon } from '../dg/icon';
import { Done, InvalidLink } from './confirm-form';
import { planSentence, type PlanChoice } from '@/lib/plans';

const initial: AuthState = { status: 'idle' };
const FORM = 'flex max-w-form flex-col gap-5 rounded-lg border border-transparent bg-surface p-5 sm:p-7';

const MESSAGE: Partial<Record<AuthState['status'], string>> = {
  invalid: 'That does not look like an e-mail address.',
  wrong: 'The e-mail address or the password is wrong.',
  not_verified: 'Confirm your e-mail address first: open the link we sent you. To get a new link, create the account again.',
  rate_limited: 'Too many attempts. Wait a little and try again.',
  unavailable: 'The service is temporarily unavailable. Try again in a few minutes.',
  terms: 'Tick the box to accept the terms of use and the privacy notice.',
};

function Alert({ text }: { text?: string }) {
  if (!text) return null;
  return <p role="alert" className="m-0 flex items-center gap-1 text-small text-alert"><Icon icon={CircleAlert} size="inline" />{text}</p>;
}

function Sent({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div role="status" className="flex max-w-form flex-col items-start gap-3 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
      <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={MailCheck} /></span>
      <h2 className="m-0 text-h3">{title}</h2>
      <p className="m-0 text-body text-ink-muted">{children}</p>
    </div>
  );
}

function Email({ state }: { state: AuthState }) {
  return (
    <TextInput
      name="email" type="email" autoComplete="email" inputMode="email" maxLength={254} required
      label="E-mail address" defaultValue={state.email ?? ''} key={state.email ?? 'new'}
      error={state.status === 'invalid' ? MESSAGE.invalid : undefined}
    />
  );
}

const PASSWORD_HINT = 'At least 12 characters. A few unrelated words are long and easy to remember. No other rules.';

export function NewPassword({ state, label = 'Password' }: { state: AuthState; label?: string }) {
  return (
    <TextInput
      name="password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required
      label={label} hint={PASSWORD_HINT}
      error={state.status === 'password' ? `Choose another password: ${state.message ?? 'this one is not accepted'}.` : undefined}
    />
  );
}

export function SignInForm({ next = null }: { next?: string | null }) {
  const [state, action, pending] = useActionState(signIn, initial);
  return (
    <form action={action} noValidate className={FORM}>
      {next && <input type="hidden" name="next" value={next} />}
      <Email state={state} />
      <TextInput name="password" type="password" autoComplete="current-password" maxLength={1024} required label="Password" />
      <Alert text={state.status !== 'invalid' ? MESSAGE[state.status] : undefined} />
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" disabled={pending}>{pending ? 'Signing in' : 'Sign in'}</Button>
        <Link href="/reset" className="text-small font-semibold">Forgot your password?</Link>
      </div>
    </form>
  );
}

export function SecondStepForm({ next = null }: { next?: string | null }) {
  const [state, action, pending] = useActionState(signInSecondStep, initial);
  if (state.status === 'expired') return <InvalidLink again={{ href: '/signin', label: 'Sign in again' }} />;
  return (
    <form action={action} noValidate className={FORM}>
      {next && <input type="hidden" name="next" value={next} />}
      <TextInput
        name="code" autoComplete="one-time-code" inputMode="text" maxLength={32} required autoFocus
        label="Code" hint="The six digits your authenticator app shows now, or one of your recovery codes."
        error={state.status === 'wrong' ? 'That code is not valid.' : undefined}
      />
      <Alert text={state.status !== 'wrong' ? MESSAGE[state.status] : undefined} />
      <div><Button type="submit" disabled={pending}>{pending ? 'Checking' : 'Continue'}</Button></div>
    </form>
  );
}

export function RegisterForm({ termsVersion, privacyVersion, choice = null, payOpen = false }: {
  termsVersion: string; privacyVersion: string; choice?: PlanChoice | null; payOpen?: boolean;
}) {
  const [state, action, pending] = useActionState(register, initial);
  if (state.status === 'sent') {
    return (
      <Sent title="Check your mail">
        We have sent a message to the address you gave. Open the link in it to confirm the address; it works once and expires in 24 hours.
        If the address already has an account, the message says so instead.{choice && <> {planSentence(choice, payOpen)}</>}
      </Sent>
    );
  }
  return (
    <form action={action} noValidate className={FORM}>
      {choice && (
        <>
          <p className="m-0 text-body font-semibold" data-plan-choice>{planSentence(choice, payOpen)}</p>
          <input type="hidden" name="plan" value={choice.plan} />
          {choice.billing && <input type="hidden" name="billing" value={choice.billing} />}
        </>
      )}
      <Email state={state} />
      <NewPassword state={state} />
      <Alert text={!['invalid', 'password'].includes(state.status) ? MESSAGE[state.status] : undefined} />
      <input type="hidden" name="termsVersion" value={termsVersion} />
      <input type="hidden" name="privacyVersion" value={privacyVersion} />
      <Choice
        name="acceptTerms" required
        label={<>I act for a trade, business or profession, and I accept the <Link href="/terms" className="font-semibold">terms of use</Link> (version {termsVersion}).</>}
        hint={`How we handle your e-mail address and password is in the privacy notice (version ${privacyVersion}).`}
      />
      <div><Button type="submit" disabled={pending}>{pending ? 'Creating' : 'Create account'}</Button></div>
    </form>
  );
}

export function ResetRequestForm() {
  const [state, action, pending] = useActionState(requestReset, initial);
  if (state.status === 'sent') {
    return (
      <Sent title="Check your mail">
        If the address has an account, a link to set a new password is on its way. It works once and expires in one hour.
      </Sent>
    );
  }
  return (
    <form action={action} noValidate className={FORM}>
      <Email state={state} />
      <Alert text={state.status !== 'invalid' ? MESSAGE[state.status] : undefined} />
      <div><Button type="submit" disabled={pending}>{pending ? 'Sending' : 'Send the link'}</Button></div>
    </form>
  );
}

export function ResetForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState(setNewPassword, initial);
  if (state.status === 'expired') return <InvalidLink again={{ href: '/reset', label: 'Ask for a new link' }} />;
  if (state.status === 'done') {
    return <Done title="Your new password is set">Every browser that was signed in to your account has been signed out. Sign in with the new password.</Done>;
  }
  return (
    <form action={action} noValidate className={FORM}>
      <input type="hidden" name="token" value={token} />
      <NewPassword state={state} label="New password" />
      <Alert text={state.status !== 'password' ? MESSAGE[state.status] : undefined} />
      <div><Button type="submit" disabled={pending}>{pending ? 'Saving' : 'Set the new password'}</Button></div>
    </form>
  );
}
