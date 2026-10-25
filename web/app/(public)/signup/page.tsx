import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { getAccountStatus, getCurrentUser } from '@/lib/account';
import { planSentence, readPlanChoice } from '@/lib/plans';
import { buildMetadata } from '@/lib/seo';
import { ContentPage } from '@/components/dg/content-page';
import { AccountsClosed } from '@/components/account/accounts-closed';
import { RegisterForm } from '@/components/account/signin-form';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = buildMetadata({
  title: 'Create an account',
  description: 'Create a DefenceGate account with your e-mail address and a password, to save searches, follow buyers and keep a shortlist.',
  path: '/signup',
  noindex: true,
});

type Props = { searchParams: Promise<{ plan?: string | string[]; billing?: string | string[] }> };

/**
 * Registration (WP-123; was /register). The pricing page's buttons land here with ?plan=&billing= (WP-122): the choice is
 * shown, sent with the registration, remembered on the account and said again after the confirmation link. No payment.
 */
export default async function SignUpPage({ searchParams }: Props) {
  const q = await searchParams;
  const choice = readPlanChoice(q.plan, q.billing);
  const [status, user] = await Promise.all([getAccountStatus(), getCurrentUser()]);
  if (user) redirect('/app');
  const open = status.open && status.termsVersion && status.privacyVersion;
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Create an account', href: '/signup' }]}
      title="Create an account"
      lead={open ? 'With your e-mail address and a password. We send a link to confirm the address.' : undefined}
    >
      {open ? (
        <>
          <RegisterForm termsVersion={status.termsVersion!} privacyVersion={status.privacyVersion!} choice={choice} />
          <p className="m-0 text-body text-ink-muted">Already have an account? <Link href="/signin" className="font-semibold">Sign in</Link>.</p>
        </>
      ) : (
        <>
          {choice && <p className="m-0 max-w-prose text-body" data-plan-choice>{planSentence(choice)}</p>}
          <AccountsClosed />
        </>
      )}
    </ContentPage>
  );
}
