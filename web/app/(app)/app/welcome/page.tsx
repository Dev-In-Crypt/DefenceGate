import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { getCurrentUser } from '@/lib/account';
import { Button } from '@/components/dg/button';
import { ProfileFields } from '@/components/account/profile-fields';
import { AppHeader, Notice } from '@/components/account/ui';
import { saveWelcome } from '../actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Welcome', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[] }> };

export default async function WelcomePage({ searchParams }: Props) {
  const [me, { n }] = await Promise.all([getCurrentUser(), searchParams]);
  // The layout has already sent anyone without a session away; this only covers a race.
  if (!me) redirect('/auth/expired');
  if (me.onboarded) redirect('/app');
  return (
    <>
      <AppHeader title="Welcome" lead="Five choices, about a minute. The defaults are fine and you can change all of them later in Settings." />
      <Notice code={n} />
      <form action={saveWelcome} className="flex max-w-form flex-col gap-6 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
        <ProfileFields profile={me.profile} />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit">Save and continue</Button>
          <Link href="/app" className="inline-flex min-h-11 items-center text-small font-bold">Skip for now</Link>
        </div>
      </form>
    </>
  );
}
