import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { getAccountStatus, getCurrentUser } from '@/lib/account';
import { buildMetadata } from '@/lib/seo';
import { safeReturnPath } from '@/lib/safe-url';
import { Callout } from '@/components/dg/blocks';
import { Button } from '@/components/dg/button';
import { ContentPage } from '@/components/dg/content-page';
import { SignInForm } from '@/components/account/signin-form';

// Reads the session cookie, so never cached; and nothing here is for a search engine.
export const dynamic = 'force-dynamic';
export const metadata: Metadata = buildMetadata({
  title: 'Sign in',
  description: 'Sign in to DefenceGate with your e-mail address and a one-time link, to save searches, follow buyers and keep a shortlist. No password.',
  path: '/signin',
  noindex: true,
});

type Props = { searchParams: Promise<{ next?: string | string[] }> };

export default async function SignInPage({ searchParams }: Props) {
  // WP-116: the /app page that sent the visitor here; the form carries it, and sign-in returns there (lib/safe-url.ts: /app only)
  const raw = (await searchParams).next;
  const next = safeReturnPath(Array.isArray(raw) ? raw[0] : raw);
  const [status, user] = await Promise.all([getAccountStatus(), getCurrentUser()]);
  if (user) redirect(next ?? '/app');
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Sign in', href: '/signin' }]}
      title="Sign in"
      lead={status.open ? 'Enter your e-mail address and we send you a link. No password to remember.' : undefined}
    >
      {status.open && status.termsVersion && status.privacyVersion ? (
        <SignInForm termsVersion={status.termsVersion} privacyVersion={status.privacyVersion} next={next} />
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
