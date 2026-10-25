import type { Metadata } from 'next';
import { cookies } from 'next/headers';
import { isTokenShaped, SECOND_STEP_COOKIE } from '@/lib/account';
import { safeReturnPath } from '@/lib/safe-url';
import { ContentPage } from '@/components/dg/content-page';
import { InvalidLink } from '@/components/account/confirm-form';
import { SecondStepForm } from '@/components/account/signin-form';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Sign-in code', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ next?: string | string[] }> };

/** The second step: only after the password, while the 5-minute ticket cookie lives. `next` (an /app page) is carried on. */
export default async function SecondStepPage({ searchParams }: Props) {
  const raw = (await searchParams).next;
  const next = safeReturnPath(Array.isArray(raw) ? raw[0] : raw);
  const ticket = (await cookies()).get(SECOND_STEP_COOKIE)?.value;
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Sign in', href: '/signin' }]}
      title="Enter your code"
      lead="Two-step sign-in is on for this account."
    >
      {isTokenShaped(ticket) ? <SecondStepForm next={next} /> : <InvalidLink again={{ href: '/signin', label: 'Sign in again' }} />}
    </ContentPage>
  );
}
