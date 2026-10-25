import type { Metadata } from 'next';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { safeReturnPath } from '@/lib/safe-url';
import { LogOut } from 'lucide-react';
import { getAccountStatus, getUserState } from '@/lib/account';
import { billingOpen, PLAN_LABELS } from '@/lib/plans';
import { BILLING_OPEN } from '@/lib/pricing';
import { AppNav } from '@/components/account/app-nav';
import { Button } from '@/components/dg/button';
import { ErrorState } from '@/components/dg/feedback';
import { Logo } from '@/components/dg/logo';
import { ThemeToggle } from '@/components/dg/theme-toggle';
import { acceptCurrentTerms, signOut } from './actions';

// Everything here depends on the session cookie: never cached, never indexed.
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { robots: { index: false, follow: false } };

function SignOut() {
  return (
    <form action={signOut}>
      <Button type="submit" variant="secondary" icon={LogOut} fullWidth>Sign out</Button>
    </form>
  );
}

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const state = await getUserState();
  // WP-116: sign-in returns to the page asked for (middleware.ts forwards the path; safeReturnPath keeps it to /app pages)
  const asked = state.kind === 'anonymous' || state.kind === 'unauthorized' ? safeReturnPath((await headers()).get('x-dg-path')) : null;
  const next = asked && asked !== '/app' ? `?next=${encodeURIComponent(asked)}` : '';
  if (state.kind === 'anonymous') redirect(`/signin${next}`);
  // Server components cannot clear cookies: /auth/expired does, then goes to /signin.
  if (state.kind === 'unauthorized') redirect(`/auth/expired${next}`);

  const skip = (
    <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-pill focus:bg-surface focus:px-5 focus:py-3 focus:font-bold">
      Skip to content
    </a>
  );

  // The API did not answer. The session may be fine, so nothing is cleared and no page below is rendered.
  if (state.kind === 'unavailable') {
    return (
      <>
        {skip}
        <div className="page flex flex-col gap-6 py-4">
          <Logo href="/" />
          <main id="main">
            <ErrorState title="Your account is not available right now" retryHref="/app">
              Your session is still valid. The service did not answer. Try again in a moment.
            </ErrorState>
          </main>
        </div>
      </>
    );
  }

  const { email, termsCurrent, plan, planChoice } = state.user;
  // WP-124: a paid plan chosen on the pricing page and not paid yet: the next step is payment, said on every account page.
  const toPay = plan === 'free' && planChoice && planChoice.plan !== 'free' && BILLING_OPEN;
  // A new version of the terms or the privacy notice: asked again here, as the sign-in form does.
  const status = termsCurrent && !toPay ? null : await getAccountStatus();
  const payNow = toPay && status && billingOpen(BILLING_OPEN, status) ? planChoice : null;
  return (
    <>
      {skip}
      <div className="page py-4 lg:grid lg:grid-cols-[240px_minmax(0,1fr)] lg:items-start lg:gap-12">
        {/* Below lg: logo, theme and a native disclosure menu (works without script). */}
        <header className="mb-6 flex flex-col gap-2 lg:hidden">
          <div className="flex items-center justify-between gap-3 rounded-pill bg-surface py-3 pl-6 pr-3">
            <Logo href="/" />
            <ThemeToggle />
          </div>
          <details className="group rounded-lg border border-transparent bg-surface">
            <summary className="flex min-h-11 cursor-pointer list-none items-center px-6 text-body font-bold [&::-webkit-details-marker]:hidden">Menu</summary>
            <div className="flex flex-col gap-4 px-3 pb-4">
              <AppNav label="Account menu" />
              <SignOut />
            </div>
          </details>
        </header>

        <aside className="sticky top-4 hidden flex-col gap-6 rounded-lg border border-transparent bg-surface p-4 lg:flex">
          <div className="flex items-center justify-between gap-2 px-2">
            <Logo href="/" />
            <ThemeToggle />
          </div>
          <AppNav />
          <div className="flex flex-col gap-3 border-t border-line pt-4">
            <p className="m-0 truncate px-2 text-small text-ink-muted" title={email}>{email}</p>
            <SignOut />
          </div>
        </aside>

        <main id="main" className="flex min-w-0 flex-col gap-6">
          {payNow && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-transparent bg-surface p-5" data-pay-now>
              <p className="m-0 text-body">You chose {PLAN_LABELS[payNow.plan]}{payNow.billing ? `, ${payNow.billing}` : ''}. Your plan is Free until it is paid.</p>
              <Button href={`/app/billing${payNow.billing ? `?plan=${payNow.plan}&billing=${payNow.billing}` : ''}`}>Continue to payment</Button>
            </div>
          )}
          {!termsCurrent && status?.termsVersion && status.privacyVersion && (
            <form action={acceptCurrentTerms} className="flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5">
              <p className="m-0 text-body">
                The <a href="/terms" className="font-semibold">terms of use</a> (version {status.termsVersion}) and the{' '}
                <a href="/privacy" className="font-semibold">privacy notice</a> (version {status.privacyVersion}) have changed. Please accept them to go on using your account.
              </p>
              <input type="hidden" name="termsVersion" value={status.termsVersion} />
              <input type="hidden" name="privacyVersion" value={status.privacyVersion} />
              <div><Button type="submit">Accept</Button></div>
            </form>
          )}
          {children}
        </main>
      </div>
    </>
  );
}
