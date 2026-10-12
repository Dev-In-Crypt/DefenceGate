'use client';

import { useEffect, useState } from 'react';
import type { StateItem, StateKey } from '@/lib/types';
import { accountSnapshot, type Snapshot, type SnapshotMode } from './actions';
import { useAccountsOpen } from './accounts-open';

/**
 * Islands on a public page learn what the account has saved by asking a server action on mount. Keys asked for
 * in the same tick go out as one call (the action takes up to 50), so a page with several islands makes one.
 * Nothing is kept between pages and nothing is written to browser storage.
 */
type Waiter = { key: StateKey | null; resolve: (s: Snapshot) => void };
let queue: Waiter[] = [];
let scheduled = false;

function flush() {
  const batch = queue;
  queue = [];
  scheduled = false;
  const seen = new Set<string>();
  const keys: StateKey[] = [];
  for (const w of batch) {
    if (!w.key) continue;
    const id = `${w.key.type}/${w.key.kind}/${w.key.ref}`;
    if (!seen.has(id)) { seen.add(id); keys.push(w.key); }
  }
  accountSnapshot(keys).then(
    (snap) => batch.forEach((w) => w.resolve(snap)),
    () => batch.forEach((w) => w.resolve({ mode: 'unavailable', items: [] })),
  );
}

function request(key: StateKey | null): Promise<Snapshot> {
  return new Promise((resolve) => {
    queue.push({ key, resolve });
    if (!scheduled) { scheduled = true; setTimeout(flush, 0); }
  });
}

export type IslandMode = 'loading' | SnapshotMode;

/** `key` null: only "is there a session" is wanted (the save-search island). */
export function useAccountState(key: StateKey | null): { mode: IslandMode; item: StateItem | null } {
  const open = useAccountsOpen();
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const type = key?.type;
  const kind = key?.kind;
  const ref = key?.ref;
  useEffect(() => {
    if (!open) return;
    let live = true;
    request(type && kind && ref ? { type, kind, ref } : null).then((s) => { if (live) setSnap(s); });
    return () => { live = false; };
  }, [open, type, kind, ref]);
  const item = snap?.items.find((i) => i.type === type && i.kind === kind && i.ref === ref) ?? null;
  // Accounts closed: there is no session to ask about, so the answer is known at once.
  return { mode: !open ? 'anonymous' : snap?.mode ?? 'loading', item };
}
