'use client';

import { useActionState } from 'react';
import { CircleAlert, CircleCheck } from 'lucide-react';
import { confirmAddress, type ConfirmState } from '@/app/(public)/auth/verify/actions';
import { Button } from '../dg/button';
import { Icon } from '../dg/icon';
import { planSentence } from '@/lib/plans';

const initial: ConfirmState = { status: 'idle' };

/** The invalid-link message is the same for every cause. Used by the pages too (missing token). */
export function InvalidLink({ again = { href: '/signup', label: 'Create the account again' } }: { again?: { href: string; label: string } }) {
  return (
    <div role="alert" className="flex max-w-form flex-col items-start gap-3 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
      <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-alert"><Icon icon={CircleAlert} /></span>
      <h2 className="m-0 text-h3">This link is no longer valid</h2>
      <p className="m-0 text-body text-ink-muted">Links work once and expire. Ask for a new one.</p>
      <Button href={again.href}>{again.label}</Button>
    </div>
  );
}

/** A finished step: the address is confirmed or the password is set. Signing in is the next step. */
export function Done({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div role="status" className="flex max-w-form flex-col items-start gap-3 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
      <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={CircleCheck} /></span>
      <h2 className="m-0 text-h3">{title}</h2>
      <p className="m-0 text-body text-ink-muted">{children}</p>
      <Button href="/signin">Sign in</Button>
    </div>
  );
}

export function ConfirmForm({ token, payOpen = false }: { token: string; payOpen?: boolean }) {
  const [state, action, pending] = useActionState(confirmAddress, initial);
  if (state.status === 'invalid') return <InvalidLink />;
  if (state.status === 'done') {
    return (
      <Done title="Your address is confirmed">
        {state.choice && <><span data-plan-choice>{planSentence(state.choice, payOpen)}</span> </>}Sign in with your e-mail address and password.
      </Done>
    );
  }
  return (
    <form action={action} className="flex max-w-form flex-col gap-4 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
      <p className="m-0 text-body text-ink-muted">Confirm that this e-mail address is yours to finish creating your account.</p>
      <input type="hidden" name="token" value={token} />
      {state.status === 'unavailable' && (
        <p role="alert" className="m-0 flex items-center gap-1 text-small text-alert">
          <Icon icon={CircleAlert} size="inline" />The service is temporarily unavailable. Try again in a few minutes.
        </p>
      )}
      <div><Button type="submit" disabled={pending}>{pending ? 'Confirming' : 'Confirm my address'}</Button></div>
    </form>
  );
}
