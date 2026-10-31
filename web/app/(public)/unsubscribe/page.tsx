import type { Metadata } from 'next';
import Link from 'next/link';
import { Button } from '@/components/dg/button';
import { ContentPage } from '@/components/dg/content-page';
import { stopDigest } from './actions';

// The URL carries the stop token of one member's digest or one account's alerts: never cached, never indexed, never sent on
// as a referrer. The proxy drops the `token` parameter from its logs (infra/caddy/Caddyfile).
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Stop e-mails', robots: { index: false, follow: false }, referrer: 'no-referrer' };

type Props = { searchParams: Promise<{ token?: string | string[]; kind?: string | string[]; done?: string; failed?: string }> };

const COPY = {
  digest: {
    title: 'Stop the weekly digest',
    ask: 'Stop the weekly digest your association sends you through DefenceGate? Nothing else changes.',
    button: 'Stop the digest',
    done: 'Done: the weekly digest is not sent to you any more. To have it again, sign in and choose it under',
    where: { href: '/app/association', label: 'Association' },
    invalid: 'This link is not complete. Use the link at the end of a digest mail, or sign in and change the digest under',
  },
  // WP-161: the stop link of a saved-search alert mail
  alerts: {
    title: 'Stop the e-mail alerts',
    ask: 'Stop every e-mail alert of your saved searches? The searches stay in your account.',
    button: 'Stop the alerts',
    done: 'Done: no more e-mail alerts are sent for your saved searches. To have them again, sign in and choose how often under',
    where: { href: '/app/searches', label: 'Saved searches' },
    invalid: 'This link is not complete. Use the link at the end of an alert mail, or sign in and change the alerts under',
  },
};

/** WP-158: the stop link of an association's weekly digest mail; WP-161: and of an alert mail. Opening it changes nothing;
 * the button does. */
export default async function UnsubscribePage({ searchParams }: Props) {
  const sp = await searchParams;
  const token = Array.isArray(sp.token) ? sp.token[0] : sp.token;
  const kind = (Array.isArray(sp.kind) ? sp.kind[0] : sp.kind) === 'alerts' ? 'alerts' : 'digest';
  const c = COPY[kind];
  const valid = typeof token === 'string' && /^[0-9a-f]{64}$/.test(token);
  const where = <Link href={c.where.href} className="font-semibold">{c.where.label}</Link>;
  return (
    <ContentPage crumbs={[{ label: 'Home', href: '/' }]} title={c.title}>
      {sp.done ? (
        <p className="m-0 max-w-prose text-body" role="status" data-unsubscribed>
          {c.done} {where}.
        </p>
      ) : sp.failed ? (
        <p className="m-0 max-w-prose text-body text-alert" role="alert">That did not work. Try the link again in a moment.</p>
      ) : valid ? (
        <form action={stopDigest} className="flex flex-col items-start gap-4">
          <p className="m-0 max-w-prose text-body">{c.ask}</p>
          <input type="hidden" name="token" value={token} />
          <input type="hidden" name="kind" value={kind} />
          <Button type="submit">{c.button}</Button>
        </form>
      ) : (
        <p className="m-0 max-w-prose text-body text-ink-muted" data-unsubscribe-invalid>
          {c.invalid} {where}.
        </p>
      )}
    </ContentPage>
  );
}
