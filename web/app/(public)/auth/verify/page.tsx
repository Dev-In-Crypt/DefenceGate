import type { Metadata } from 'next';
import { getAccountStatus, isTokenShaped } from '@/lib/account';
import { billingOpen } from '@/lib/plans';
import { BILLING_OPEN } from '@/lib/pricing';
import { ContentPage } from '@/components/dg/content-page';
import { ConfirmForm, InvalidLink } from '@/components/account/confirm-form';

// The URL carries a one-time token: never cached, never indexed, never sent on as a referrer.
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Confirm your address', robots: { index: false, follow: false }, referrer: 'no-referrer' };

type Props = { searchParams: Promise<{ token?: string | string[] }> };

/** Rendering this page does not consume the token: mail scanners open links. The button does. */
export default async function VerifyPage({ searchParams }: Props) {
  const [{ token: raw }, status] = await Promise.all([searchParams, getAccountStatus()]);
  const token = Array.isArray(raw) ? raw[0] : raw;
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Create an account', href: '/signup' }]}
      title="Confirm your address"
    >
      {isTokenShaped(token) ? <ConfirmForm token={token} payOpen={billingOpen(BILLING_OPEN, status)} /> : <InvalidLink />}
    </ContentPage>
  );
}
