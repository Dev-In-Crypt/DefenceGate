import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { getAccountStatus, getCurrentUser } from '@/lib/account';
import { Callout } from '@/components/dg/blocks';
import { Button } from '@/components/dg/button';
import { ContentPage } from '@/components/dg/content-page';
import { SignInForm } from '@/components/account/signin-form';

// Reads the session cookie, so never cached; and nothing here is for a search engine.
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Sign in', robots: { index: false, follow: false } };

export default async function SignInPage() {
  const [status, user] = await Promise.all([getAccountStatus(), getCurrentUser()]);
  if (user) redirect('/app');
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Sign in', href: '/signin' }]}
      title="Sign in"
      lead={status.open ? 'Enter your e-mail address and we send you a link. No password to remember.' : undefined}
    >
      {status.open ? (
        <SignInForm />
      ) : (
        <Callout title="Sign-in is not open yet">
          <p className="m-0">Accounts are not available at the moment. Browsing tenders, buyers and funding calls needs no account.</p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Button href="/tenders" variant="secondary">Browse tenders</Button>
            <Button href="/funding" variant="secondary">Browse funding calls</Button>
          </div>
        </Callout>
      )}
    </ContentPage>
  );
}
