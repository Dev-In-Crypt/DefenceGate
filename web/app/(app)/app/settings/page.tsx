import type { Metadata } from 'next';
import Link from 'next/link';
import { Download } from 'lucide-react';
import { dataOrNull, getCurrentUser, listSessions } from '@/lib/account';
import { formatStamp } from '@/lib/account-format';
import { planSentence } from '@/lib/plans';
import { Button } from '@/components/dg/button';
import { TextInput } from '@/components/dg/form';
import { Tag } from '@/components/dg/tag';
import { ProfileFields } from '@/components/account/profile-fields';
import { TotpSettings } from '@/components/account/totp-settings';
import { AppHeader, Block, LoadFailed, Notice } from '@/components/account/ui';
import { changeMyPassword, deleteAccount, endOtherSessions, endSession, saveSettings, signOutEverywhere } from '../actions';

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
      <AppHeader title="Settings" lead="Your profile, your password and two-step sign-in, the devices signed in to your account, and your data." />
      <Notice code={n} />

      <Block id="profile" title="Profile" aside={<span className="max-w-full truncate text-small text-ink-muted">{me.email}</span>}>
        <form action={saveSettings} className="flex max-w-form flex-col gap-6">
          <ProfileFields profile={me.profile} />
          <div><Button type="submit">Save profile</Button></div>
        </form>
      </Block>

      <Block id="plan" title="Plan">
        <p className="m-0 max-w-prose text-body text-ink-muted" data-plan-choice>
          Your plan is Free.{me.planChoice && me.planChoice.plan !== 'free' && <> {planSentence(me.planChoice)} Nothing is charged until then.</>}
        </p>
      </Block>

      <Block id="password" title="Password">
        {me.hasPassword ? (
          <form action={changeMyPassword} className="flex max-w-form flex-col gap-4">
            <TextInput name="currentPassword" type="password" autoComplete="current-password" maxLength={1024} required label="Current password" />
            <TextInput name="newPassword" type="password" autoComplete="new-password" minLength={12} maxLength={128} required
              label="New password" hint="At least 12 characters. A few unrelated words are long and easy to remember. Every other browser is signed out." />
            <div><Button type="submit" variant="secondary">Change password</Button></div>
          </form>
        ) : (
          <p className="m-0 max-w-prose text-body text-ink-muted">
            This account was made before passwords were introduced and has none yet. Set one through <Link href="/reset" className="font-semibold">Forgot your password</Link>.
          </p>
        )}
      </Block>

      <Block id="two-step" title="Two-step sign-in">
        {me.hasPassword ? <TotpSettings enabled={me.totp} /> : <p className="m-0 text-body text-ink-muted">Set a password first.</p>}
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
        <div className="flex flex-wrap gap-3">
          {others.length > 1 && (
            <form action={endOtherSessions}><Button type="submit" variant="secondary">Sign out all other sessions</Button></form>
          )}
          <form action={signOutEverywhere}><Button type="submit" variant="secondary">Sign out everywhere</Button></form>
        </div>
      </Block>

      <Block id="data" title="Download my data">
        <p className="m-0 max-w-prose text-body text-ink-muted">Everything held about this account as one JSON file: your address, profile and chosen plan, saved searches, shortlist and follows, your sessions, and when your address was confirmed, your password last changed and two-step sign-in turned on (never the password or keys themselves).</p>
        <form method="post" action="/app/settings/export">
          <Button type="submit" variant="secondary" icon={Download}>Download my data</Button>
        </form>
      </Block>

      <Block id="delete" title="Delete account">
        <p className="m-0 max-w-prose text-body text-ink-muted">Deleting the account removes at once, and for good:</p>
        <ul className="m-0 flex max-w-prose list-disc flex-col gap-1 pl-5 text-body text-ink-muted" data-deletes>
          <li>your e-mail address, your profile and the plan you chose;</li>
          <li>your saved searches and their alerts, your shortlist with its notes, and what you follow;</li>
          <li>your password, two-step sign-in key and recovery codes, and any confirmation or password link not used yet;</li>
          <li>every session: you are signed out everywhere.</li>
        </ul>
        <p className="m-0 max-w-prose text-body text-ink-muted">
          It cannot be undone. Download your data first if you want a copy. The counters that limit sign-in attempts hold no
          address in readable form and expire within a day.
        </p>
        <form action={deleteAccount} className="flex max-w-form flex-col gap-4">
          <TextInput name="confirm" type="email" autoComplete="off" required maxLength={254}
            label="Type your e-mail address to confirm" hint="The same address you sign in with." />
          {me.hasPassword && (
            <TextInput name="password" type="password" autoComplete="current-password" required maxLength={1024} label="Account password" />
          )}
          <div><Button type="submit" variant="secondary" className="border-alert text-alert">Delete my account</Button></div>
        </form>
      </Block>
    </>
  );
}
