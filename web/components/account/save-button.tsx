'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Bell, BellRing, Bookmark, BookmarkCheck, type LucideIcon } from 'lucide-react';
import type { FollowKind, ShortlistKind } from '@/lib/types';
import { Button } from '../dg/button';
import { setFollowed, setShortlisted, type ActionOutcome, type SnapshotMode } from './actions';
import { useAccountsOpen } from './accounts-open';
import { useAccountState } from './use-account-state';

/**
 * Shared body of the shortlist and follow toggles. The visible label stays the same and the state is carried
 * by aria-pressed, the icon and the fill. Before the answer arrives the button is inert, never missing.
 */
function Toggle({ type, kind, refId, label, signInLabel, icons, doneText, doneHref, doneLink, send, className }: {
  type: 'shortlist' | 'follow'; kind: string; refId: string; label: string; signInLabel: string;
  icons: { off: LucideIcon; on: LucideIcon };
  doneText: [on: string, off: string]; doneHref: string; doneLink: string;
  send: (on: boolean) => Promise<ActionOutcome>;
  className?: string;
}) {
  const open = useAccountsOpen();
  const { mode, item } = useAccountState({ type, kind, ref: refId });
  const [local, setLocal] = useState<{ on?: boolean; mode?: SnapshotMode; note?: string; error?: string } | null>(null);
  const [busy, setBusy] = useState(false);

  // While sign-in is closed the button would lead nowhere: it is not shown at all.
  if (!open) return null;

  const effective = local?.mode ?? mode;
  const on = local?.on ?? item?.saved ?? false;

  if (effective === 'anonymous') {
    return <Button href="/signin" variant="secondary" icon={icons.off} className={className}>{signInLabel}</Button>;
  }
  if (effective === 'unavailable') {
    return <span className="inline-flex min-h-11 items-center text-small text-ink-muted">Saving is unavailable right now.</span>;
  }

  const click = async () => {
    setBusy(true);
    try {
      const r = await send(!on);
      if (r.ok) setLocal({ on: r.on, note: doneText[r.on ? 0 : 1] });
      else setLocal({ mode: r.mode === 'ready' ? undefined : r.mode, on, error: r.message ?? 'That did not work. Try again.' });
    } catch {
      setLocal({ on, error: 'That did not work. Try again.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        variant={on ? 'primary' : 'secondary'} icon={on ? icons.on : icons.off} className={className}
        aria-pressed={on} aria-busy={effective === 'loading' || busy} disabled={effective === 'loading' || busy} onClick={click}
      >
        {label}
      </Button>
      <span role="status" className="min-h-5 text-small text-ink-muted">
        {local?.error ? <span className="text-alert">{local.error}</span> : local?.note ? (
          <>{local.note} <Link href={doneHref} className="font-semibold">{doneLink}</Link></>
        ) : null}
      </span>
    </div>
  );
}

/** Adds a tender or funding call to the shortlist, or removes it. `refId` is the notice's or call's id. */
export function SaveButton({ kind, refId, className }: { kind: ShortlistKind; refId: string; className?: string }) {
  return (
    <Toggle
      type="shortlist" kind={kind} refId={refId} label="Shortlist" signInLabel="Sign in to save" className={className}
      icons={{ off: Bookmark, on: BookmarkCheck }}
      doneText={['Added to your shortlist.', 'Removed from your shortlist.']} doneHref="/app/shortlist" doneLink="Open shortlist"
      send={(on) => setShortlisted(kind, refId, on)}
    />
  );
}

/** Follows a buyer (`refId` = buyer id) or a programme (`refId` = programme code), or stops. */
export function FollowButton({ kind, refId, label, className }: { kind: FollowKind; refId: string; label?: string; className?: string }) {
  return (
    <Toggle
      type="follow" kind={kind} refId={refId} label={label ?? (kind === 'buyer' ? 'Follow this buyer' : 'Follow this programme')} signInLabel="Sign in to follow" className={className}
      icons={{ off: Bell, on: BellRing }}
      doneText={['You now follow this.', 'You no longer follow this.']} doneHref="/app/following" doneLink="Open following"
      send={(on) => setFollowed(kind, refId, on)}
    />
  );
}
