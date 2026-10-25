import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { getAccountStatus, getCurrentUser } from '@/lib/account';
import { buildMetadata } from '@/lib/seo';
import { safeReturnPath } from '@/lib/safe-url';
import { ContentPage } from '@/components/dg/content-page';
import { AccountsClosed } from '@/components/account/accounts-closed';
import { SignInForm } from '@/components/account/signin-form';

// Reads the session cookie, so never cached; and nothing here is for a search engine.
export const dynamic = 'force-dynamic';
export const metadata: Metadata = buildMetadata({
  title: 'Sign in',
  description: 'Sign in to DefenceGate with your e-mail address and password, to save searches, follow buyers and keep a shortlist.',
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
      lead={status.open ? 'With your e-mail address and password.' : undefined}
    >
      {status.open ? (
        <>
          <SignInForm next={next} />
          <p className="m-0 max-w-prose text-body text-ink-muted">
            No account yet? <Link href="/signup" className="font-semibold">Create one</Link>.
          </p>
        </>
      ) : <AccountsClosed />}
    </ContentPage>
  );
}
