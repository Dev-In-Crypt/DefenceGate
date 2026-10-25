'use client';

import { useActionState } from 'react';
import { CircleAlert } from 'lucide-react';
import { confirmTotp, startTotp, stopTotp, type TotpState } from '@/app/(app)/app/actions';
import { Button } from '../dg/button';
import { TextInput } from '../dg/form';
import { Icon } from '../dg/icon';

const initial: TotpState = { status: 'idle' };
const ERRORS: Partial<Record<TotpState['status'], string>> = {
  wrong_password: 'The password is wrong.',
  invalid_code: 'That code is not valid. Check the time on your phone and try the code shown now.',
  rate_limited: 'Too many attempts. Wait a little and try again.',
  error: 'That did not work. Try again.',
};

function Alert({ status }: { status: TotpState['status'] }) {
  const text = ERRORS[status];
  if (!text) return null;
  return <p role="alert" className="m-0 flex items-center gap-1 text-small text-alert"><Icon icon={CircleAlert} size="inline" />{text}</p>;
}

const Password = () => (
  <TextInput name="password" type="password" autoComplete="current-password" maxLength={1024} required label="Your password" />
);

/** Set-up in two steps (password, then a first code), the recovery codes once, and turning it off with the password. */
export function TotpSettings({ enabled }: { enabled: boolean }) {
  const [setup, start, starting] = useActionState(startTotp, initial);
  const [done, confirm, confirming] = useActionState(confirmTotp, initial);

  if (done.status === 'on' && done.codes) {
    return (
      <div role="status" className="flex max-w-form flex-col gap-3">
        <p className="m-0 text-body font-semibold">Two-step sign-in is on.</p>
        <p className="m-0 text-body text-ink-muted">
          These recovery codes are shown only now. Keep them somewhere safe: each one signs you in once if you lose your phone.
        </p>
        <ul className="m-0 grid list-none grid-cols-2 gap-2 p-0 font-mono text-mono">
          {done.codes.map((c) => <li key={c} className="rounded-md bg-surface-inset px-3 py-2">{c}</li>)}
        </ul>
      </div>
    );
  }

  if (enabled) {
    return (
      <form action={stopTotp} className="flex max-w-form flex-col gap-4">
        <p className="m-0 text-body text-ink-muted">On. Signing in asks for a code from your authenticator app, or a recovery code.</p>
        <Password />
        <div><Button type="submit" variant="secondary">Turn off two-step sign-in</Button></div>
      </form>
    );
  }

  const shown = setup;                               // a mistyped code keeps the key on the page
  if (shown.status === 'setup' && shown.secret && shown.uri) {
    const grouped = shown.secret.replace(/(.{4})/g, '$1 ').trim();
    return (
      <form action={confirm} className="flex max-w-form flex-col gap-4">
        <p className="m-0 text-body text-ink-muted">
          1. In your authenticator app, add an account with this key (or <a href={shown.uri} className="font-semibold">open it in the app</a> on this device):
        </p>
        <p className="m-0 break-all rounded-md bg-surface-inset px-3 py-2 font-mono text-mono" aria-label="Key">{grouped}</p>
        <TextInput name="code" autoComplete="one-time-code" inputMode="numeric" maxLength={32} required
          label="2. The six-digit code the app shows" />
        <Alert status={done.status} />
        <div><Button type="submit" disabled={confirming}>{confirming ? 'Checking' : 'Turn on two-step sign-in'}</Button></div>
      </form>
    );
  }

  return (
    <form action={start} className="flex max-w-form flex-col gap-4">
      <p className="m-0 text-body text-ink-muted">
        Off. With it on, signing in asks for your password and a code from an authenticator app on your phone.
      </p>
      <Password />
      <Alert status={setup.status} />
      <div><Button type="submit" variant="secondary" disabled={starting}>{starting ? 'Checking' : 'Set up two-step sign-in'}</Button></div>
    </form>
  );
}
