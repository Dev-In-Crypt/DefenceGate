'use client';

import { useActionState } from 'react';
import { CircleAlert } from 'lucide-react';
import { confirmSignIn, type ConfirmState } from '@/app/(public)/auth/verify/actions';
import { Button } from '../dg/button';
import { Icon } from '../dg/icon';

const initial: ConfirmState = { status: 'idle' };

/** The invalid-link message is the same for every cause. Used by the page too (missing token). */
export function InvalidLink() {
  return (
    <div role="alert" className="flex max-w-form flex-col items-start gap-3 rounded-lg border border-edge bg-surface p-5 sm:p-6">
      <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-alert"><Icon icon={CircleAlert} /></span>
      <h2 className="m-0 text-h3">This link is no longer valid</h2>
      <p className="m-0 text-body text-ink-muted">Request a new one.</p>
      <Button href="/signin">Request a new link</Button>
    </div>
  );
}

export function ConfirmForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState(confirmSignIn, initial);
  if (state.status === 'invalid') return <InvalidLink />;
  return (
    <form action={action} className="flex max-w-form flex-col gap-4 rounded-lg border border-edge bg-surface p-5 sm:p-6">
      <p className="m-0 text-body text-ink-muted">Sign-in links work once, in the browser that asked for them. Confirm to sign in here.</p>
      <input type="hidden" name="token" value={token} />
      {state.status === 'unavailable' && (
        <p role="alert" className="m-0 flex items-center gap-1 text-small text-alert">
          <Icon icon={CircleAlert} size="inline" />Sign-in is temporarily unavailable. Try again in a few minutes.
        </p>
      )}
      <div><Button type="submit" disabled={pending}>{pending ? 'Signing in' : 'Confirm sign-in'}</Button></div>
    </form>
  );
}
