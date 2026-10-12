import type { Metadata } from 'next';
import { Download } from 'lucide-react';
import { dataOrNull, getCurrentUser, listSessions } from '@/lib/account';
import { formatStamp } from '@/lib/account-format';
import { Button } from '@/components/dg/button';
import { TextInput } from '@/components/dg/form';
import { Tag } from '@/components/dg/tag';
import { ProfileFields } from '@/components/account/profile-fields';
import { AppHeader, Block, LoadFailed, Notice } from '@/components/account/ui';
import { deleteAccount, endOtherSessions, endSession, saveSettings } from '../actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Settings', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[] }> };

export default async function SettingsPage({ searchParams }: Props) {
  const [me, sessionsResult, { n }] = await Promise.all([getCurrentUser(), listSessions(), searchParams]);
  const sessions = dataOrNull(sessionsResult);
  if (!me) return <LoadFailed href="/app/settings" />;
  const others = (sessions ?? []).filter((s) => !s.current);
  return (
    <>
      <AppHeader title="Settings" lead="Your profile, the devices signed in to your account, and your data." />
      <Notice code={n} />

      <Block id="profile" title="Profile" aside={<span className="max-w-full truncate text-small text-ink-muted">{me.email}</span>}>
        <form action={saveSettings} className="flex max-w-[860px] flex-col gap-6">
          <ProfileFields profile={me.profile} />
          <div><Button type="submit">Save profile</Button></div>
        </form>
      </Block>

      <Block id="sessions" title="Active sessions">
        {sessions === null ? (
          <p className="m-0 text-body text-ink-muted">The list of sessions could not be loaded. Try again in a moment.</p>
        ) : sessions.length === 0 ? (
          <p className="m-0 text-body text-ink-muted">No other sessions are active.</p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {sessions.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-surface-inset p-4">
                <div className="flex flex-col gap-1">
                  <span className="flex flex-wrap items-center gap-2 text-body font-semibold">
                    {s.current ? 'This browser' : 'Another browser'}
                    {s.current && <Tag>Current</Tag>}
                  </span>
                  <span className="font-mono text-mono text-ink-muted">
                    Signed in {formatStamp(s.createdAt)} · last seen {formatStamp(s.lastSeenAt)}
                  </span>
                </div>
                {!s.current && (
                  <form action={endSession}>
                    <input type="hidden" name="id" value={s.id} />
                    <Button type="submit" variant="secondary">Sign out this session</Button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        )}
        {others.length > 1 && (
          <form action={endOtherSessions}><Button type="submit" variant="secondary">Sign out all other sessions</Button></form>
        )}
      </Block>

      <Block id="data" title="Download my data">
        <p className="m-0 max-w-[62ch] text-body text-ink-muted">Everything held about this account as one JSON file: your profile, saved searches, shortlist and follows.</p>
        <form method="post" action="/app/settings/export">
          <Button type="submit" variant="secondary" icon={Download}>Download my data</Button>
        </form>
      </Block>

      <Block id="delete" title="Delete account">
        <p className="m-0 max-w-[62ch] text-body text-ink-muted">
          This deletes your profile, saved searches, shortlist and follows, and signs you out everywhere. It cannot be undone.
        </p>
        <form action={deleteAccount} className="flex max-w-[560px] flex-col gap-4">
          <TextInput name="confirm" type="email" autoComplete="off" required maxLength={254}
            label="Type your e-mail address to confirm" hint="The same address you sign in with." />
          <div><Button type="submit" variant="secondary" className="border-alert text-alert">Delete my account</Button></div>
        </form>
      </Block>
    </>
  );
}
