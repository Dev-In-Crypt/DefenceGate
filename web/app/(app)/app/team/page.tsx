import type { Metadata } from 'next';
import Link from 'next/link';
import { Trash2, UserPlus } from 'lucide-react';
import { dataOrNull } from '@/lib/account';
import { formatStamp } from '@/lib/account-format';
import { getWorkspace } from '@/lib/workspace';
import { Button } from '@/components/dg/button';
import { Choice, TextInput } from '@/components/dg/form';
import { Tag } from '@/components/dg/tag';
import { AppHeader, Block, LoadFailed, Notice } from '@/components/account/ui';
import { dropMember, endWorkspace, leaveTeam, sendInvite, startWorkspace, withdrawInvite } from './actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Team', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[] }> };

/** WP-157: the team workspace (Team, Consultant): members share the owner's plan, saved searches, shortlist and follows. */
export default async function TeamPage({ searchParams }: Props) {
  const [result, { n }] = await Promise.all([getWorkspace(), searchParams]);
  const state = dataOrNull(result);
  if (!state) return <LoadFailed href="/app/team" />;
  const ws = state.workspace;
  const lead = 'The people of one workspace share its owner’s plan, the saved searches, the shortlist with its statuses and notes, and the follows.';
  if (!ws) {
    return (
      <>
        <AppHeader title="Team" lead={lead} />
        <Notice code={n} />
        <Block id="start" title="Team workspace">
          {state.canCreate ? (
            <form action={startWorkspace} className="flex flex-col items-start gap-4">
              <p className="m-0 max-w-prose text-body text-ink-muted">
                Make a workspace, then invite colleagues by e-mail: {state.seats} people in all, you included. Your own saved searches, shortlist and follows become the team&apos;s.
              </p>
              <Button type="submit">Make the workspace</Button>
            </form>
          ) : (
            <p className="m-0 max-w-prose text-body text-ink-muted" data-team-plan>
              The team workspace is part of Team and Consultant. See <Link href="/app/billing" className="font-semibold">Billing</Link>. Invited to a team? Open the link in the invitation.
            </p>
          )}
        </Block>
      </>
    );
  }
  const owner = ws.role === 'owner';
  const open = ws.seats - ws.members.length - ws.invites.length;
  return (
    <>
      <AppHeader title="Team" lead={lead} />
      <Notice code={n} />
      {!ws.active && (
        <p role="status" className="m-0 max-w-prose rounded-md bg-surface p-4 text-body" data-team-paused>
          Sharing is paused: the plan in force has no team workspace. Everyone sees their own searches, shortlist and follows only. Nothing is deleted. See <Link href="/app/billing" className="font-semibold">Billing</Link>.
        </p>
      )}

      <Block id="members" title="Members" aside={<span className="font-mono text-mono text-ink-muted">{ws.members.length} of {ws.seats}</span>}>
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {ws.members.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-surface-inset p-4" data-member>
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="min-w-0 text-body font-semibold [overflow-wrap:anywhere]">{m.email}</span>
                <Tag>{m.role === 'owner' ? 'Owner' : 'Member'}</Tag>
                {m.me && <Tag>You</Tag>}
                <span className="font-mono text-mono text-ink-muted">joined {formatStamp(m.joinedAt)}</span>
              </div>
              {owner && m.role === 'member' && (
                <form action={dropMember}>
                  <input type="hidden" name="id" value={m.id} />
                  <Button type="submit" variant="text" icon={Trash2} aria-label={`Remove ${m.email} from the team`}>Remove</Button>
                </form>
              )}
            </li>
          ))}
        </ul>
      </Block>

      {owner && (
        <Block id="invite" title="Invite a colleague">
          {open > 0 ? (
            <form action={sendInvite} className="flex max-w-form flex-col gap-4" data-invite-form>
              <TextInput name="email" type="email" autoComplete="off" maxLength={320} required label="Their e-mail address"
                hint="We send one e-mail with a link. It works once, for 7 days, and only for an account with this address." />
              <div><Button type="submit" icon={UserPlus}>Send invitation</Button></div>
            </form>
          ) : (
            <p className="m-0 text-body text-ink-muted">Every place is taken. Withdraw an invitation or remove a member to invite someone else.</p>
          )}
          {ws.invites.length > 0 && (
            <ul className="m-0 mt-4 flex list-none flex-col gap-3 p-0">
              {ws.invites.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-surface-inset p-4" data-invite>
                  <span className="min-w-0 text-body [overflow-wrap:anywhere]">{i.email} <span className="font-mono text-mono text-ink-muted">· invited, until {formatStamp(i.expiresAt)}</span></span>
                  <form action={withdrawInvite}>
                    <input type="hidden" name="id" value={i.id} />
                    <Button type="submit" variant="text" icon={Trash2} aria-label={`Withdraw the invitation to ${i.email}`}>Withdraw</Button>
                  </form>
                </li>
              ))}
            </ul>
          )}
        </Block>
      )}

      {owner ? (
        <Block id="end" title="End the workspace">
          <form action={endWorkspace} className="flex max-w-prose flex-col items-start gap-3">
            <p className="m-0 text-body text-ink-muted">The members leave and the client profiles are deleted. Everyone keeps their own saved searches, shortlist and follows; the members&apos; plan ends with the workspace.</p>
            <Choice name="confirm" value="yes" label="I want to end this workspace" />
            <Button type="submit" variant="secondary">End the workspace</Button>
          </form>
        </Block>
      ) : (
        <Block id="leave" title="Leave the team">
          <form action={leaveTeam} className="flex max-w-prose flex-col items-start gap-3">
            <p className="m-0 text-body text-ink-muted">Your own saved searches, shortlist entries and follows go with you; the team&apos;s stay with the team. The plan you had through the team ends.</p>
            <Button type="submit" variant="secondary">Leave the team</Button>
          </form>
        </Block>
      )}
    </>
  );
}
