import type { Metadata } from 'next';
import { getAccountStatus } from '@/lib/account';
import { buildMetadata } from '@/lib/seo';
import { ContentPage } from '@/components/dg/content-page';
import { AccountsClosed } from '@/components/account/accounts-closed';
import { ResetRequestForm } from '@/components/account/signin-form';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = buildMetadata({
  title: 'Forgot your password',
  description: 'Set a new password for your DefenceGate account through a link sent to your e-mail address.',
  path: '/reset',
  noindex: true,
});

export default async function ResetRequestPage() {
  const status = await getAccountStatus();
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Sign in', href: '/signin' }, { label: 'Forgot your password', href: '/reset' }]}
      title="Forgot your password"
      lead={status.open ? 'Enter the address of your account. We send a link to set a new password.' : undefined}
    >
      {status.open ? <ResetRequestForm /> : <AccountsClosed />}
    </ContentPage>
  );
}
