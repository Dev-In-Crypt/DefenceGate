'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Bookmark } from 'lucide-react';
import { suggestSearchName } from '@/lib/account-format';
import type { SearchFilters, SearchKind } from '@/lib/types';
import { Button } from '../dg/button';
import { TextInput } from '../dg/form';
import { saveSearch } from './actions';
import { useAccountsOpen } from './accounts-open';
import { useAccountState } from './use-account-state';

/**
 * "Save this search" beside the filters of /tenders and /funding. `filters` are the page's own query keys
 * (defaults omitted, no page). The page itself stays static: this asks for the session after it has loaded.
 */
export function SaveSearch({ kind, filters }: { kind: SearchKind; filters: SearchFilters }) {
  const open = useAccountsOpen();
  const { mode } = useAccountState(null);
  const [step, setStep] = useState<'closed' | 'editing' | 'saving' | 'saved'>('closed');
  const [signedOut, setSignedOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;     // sign-in is closed: nothing to save to
  if (mode === 'anonymous' || signedOut) {
    return <Button href="/signin" variant="secondary" icon={Bookmark} fullWidth>Sign in to save this search</Button>;
  }
  if (mode === 'unavailable') {
    return <p className="m-0 text-small text-ink-muted">Saving searches is unavailable right now.</p>;
  }
  if (step === 'saved') {
    return (
      <p role="status" className="m-0 rounded-lg border border-edge bg-surface p-4 text-small text-ink">
        Saved. New matches appear on your dashboard. <Link href="/app/searches" className="font-semibold">Open saved searches</Link>
      </p>
    );
  }
  if (step === 'closed') {
    return (
      <Button variant="secondary" icon={Bookmark} fullWidth disabled={mode === 'loading'} aria-busy={mode === 'loading'} onClick={() => setStep('editing')}>
        Save this search
      </Button>
    );
  }

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const name = String(new FormData(e.currentTarget).get('name') ?? '');
    setStep('saving');
    setError(null);
    try {
      const r = await saveSearch(kind, name, filters);
      if (r.ok) { setStep('saved'); return; }
      if (r.mode === 'anonymous') { setSignedOut(true); return; }
      setError(r.message ?? 'Could not save this search.');
    } catch {
      setError('Could not save this search.');
    }
    setStep('editing');
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded-lg border border-edge bg-surface p-5">
      <TextInput name="name" label="Name of this search" maxLength={80} required defaultValue={suggestSearchName(kind, filters)} error={error ?? undefined} />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={step === 'saving'}>{step === 'saving' ? 'Saving' : 'Save'}</Button>
        <Button variant="text" onClick={() => { setStep('closed'); setError(null); }}>Cancel</Button>
      </div>
    </form>
  );
}
