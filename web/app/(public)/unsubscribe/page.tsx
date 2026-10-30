import type { Metadata } from 'next';
import Link from 'next/link';
import { Button } from '@/components/dg/button';
import { ContentPage } from '@/components/dg/content-page';
import { stopDigest } from './actions';

// The URL carries the stop token of one member's digest: never cached, never indexed, never sent on as a referrer. The proxy
// drops the `token` parameter from its logs (infra/caddy/Caddyfile).
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Stop the weekly digest', robots: { index: false, follow: false }, referrer: 'no-referrer' };

type Props = { searchParams: Promise<{ token?: string | string[]; done?: string; failed?: string }> };

/** WP-158: the stop link of an association's weekly digest mail. Opening it changes nothing; the button does. */
export default async function UnsubscribePage({ searchParams }: Props) {
  const sp = await searchParams;
  const token = Array.isArray(sp.token) ? sp.token[0] : sp.token;
  const valid = typeof token === 'string' && /^[0-9a-f]{64}$/.test(token);
  return (
    <ContentPage crumbs={[{ label: 'Home', href: '/' }]} title="Stop the weekly digest">
      {sp.done ? (
        <p className="m-0 max-w-prose text-body" role="status" data-unsubscribed>
          Done: the weekly digest is not sent to you any more. To have it again, sign in and choose it under <Link href="/app/association" className="font-semibold">Association</Link>.
        </p>
      ) : sp.failed ? (
        <p className="m-0 max-w-prose text-body text-alert" role="alert">That did not work. Try the link again in a moment.</p>
      ) : valid ? (
        <form action={stopDigest} className="flex flex-col items-start gap-4">
          <p className="m-0 max-w-prose text-body">Stop the weekly digest your association sends you through DefenceGate? Nothing else changes.</p>
          <input type="hidden" name="token" value={token} />
          <Button type="submit">Stop the digest</Button>
        </form>
      ) : (
        <p className="m-0 max-w-prose text-body text-ink-muted" data-unsubscribe-invalid>
          This link is not complete. Use the link at the end of a digest mail, or sign in and change the digest under <Link href="/app/association" className="font-semibold">Association</Link>.
        </p>
      )}
    </ContentPage>
  );
}
