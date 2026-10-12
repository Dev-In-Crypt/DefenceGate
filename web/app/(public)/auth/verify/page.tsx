import type { Metadata } from 'next';
import { isTokenShaped } from '@/lib/account';
import { ContentPage } from '@/components/dg/content-page';
import { ConfirmForm, InvalidLink } from '@/components/account/confirm-form';

// The URL carries a one-time token: never cached, never indexed, never sent on as a referrer.
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Confirm sign-in', robots: { index: false, follow: false }, referrer: 'no-referrer' };

type Props = { searchParams: Promise<{ token?: string | string[] }> };

/** Rendering this page does not consume the token: mail scanners open links. The button does. */
export default async function VerifyPage({ searchParams }: Props) {
  const raw = (await searchParams).token;
  const token = Array.isArray(raw) ? raw[0] : raw;
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Sign in', href: '/signin' }]}
      title="Confirm sign-in"
    >
      {isTokenShaped(token) ? <ConfirmForm token={token} /> : <InvalidLink />}
    </ContentPage>
  );
}
