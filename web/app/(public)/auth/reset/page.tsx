import type { Metadata } from 'next';
import { isTokenShaped } from '@/lib/account';
import { ContentPage } from '@/components/dg/content-page';
import { InvalidLink } from '@/components/account/confirm-form';
import { ResetForm } from '@/components/account/signin-form';

// The URL carries a one-time token: never cached, never indexed, never sent on as a referrer. The proxy drops the
// `token` parameter from its logs (infra/Caddyfile).
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Set a new password', robots: { index: false, follow: false }, referrer: 'no-referrer' };

type Props = { searchParams: Promise<{ token?: string | string[] }> };

/** Rendering this page does not use the link up: setting the password does. */
export default async function ResetPage({ searchParams }: Props) {
  const raw = (await searchParams).token;
  const token = Array.isArray(raw) ? raw[0] : raw;
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Sign in', href: '/signin' }]}
      title="Set a new password"
    >
      {isTokenShaped(token) ? <ResetForm token={token} /> : <InvalidLink again={{ href: '/reset', label: 'Ask for a new link' }} />}
    </ContentPage>
  );
}
