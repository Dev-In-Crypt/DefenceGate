import type { Metadata } from 'next';
import { isTokenShaped } from '@/lib/account';
import { Button } from '@/components/dg/button';
import { AppHeader, Block, NextStep } from '@/components/account/ui';
import { acceptInvite } from '../actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Join a team', robots: { index: false, follow: false }, referrer: 'no-referrer' };

type Props = { searchParams: Promise<{ token?: string | string[] }> };

/**
 * WP-157: the link of an invitation lands here (after sign-in: the layout sends a signed-out visitor to /signin and back). Opening
 * the page joins nothing (a mail scanner opens links too): the button does.
 */
export default async function JoinPage({ searchParams }: Props) {
  const { token } = await searchParams;
  const t = typeof token === 'string' && isTokenShaped(token) ? token : null;
  return (
    <>
      <AppHeader title="Join a team" />
      {t ? (
        <Block id="join" title="You are invited to a team workspace">
          <form action={acceptInvite} className="flex max-w-prose flex-col items-start gap-4" data-join-form>
            <input type="hidden" name="token" value={t} />
            <p className="m-0 text-body text-ink-muted">
              Members work with the plan of the workspace&apos;s owner and share their saved searches, shortlist (with statuses and notes) and follows with the team. Yours are shared too while you are a member; leaving takes them back.
            </p>
            <Button type="submit">Join the team</Button>
          </form>
        </Block>
      ) : (
        <NextStep links={[{ label: 'Your team', href: '/app/team' }]}>This link is not complete. Open the link in the invitation e-mail again, or ask for a new invitation.</NextStep>
      )}
    </>
  );
}
