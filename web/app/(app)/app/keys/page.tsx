import type { Metadata } from 'next';
import Link from 'next/link';
import { dataOrNull, listApiKeys } from '@/lib/account';
import { formatStamp } from '@/lib/account-format';
import { Button } from '@/components/dg/button';
import { TextInput } from '@/components/dg/form';
import { Tag } from '@/components/dg/tag';
import { ApiKeyCreate } from '@/components/account/api-key-create';
import { AppHeader, Block, LoadFailed, Notice } from '@/components/account/ui';
import { endApiKey } from '../actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'API keys', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[] }> };

/** WP-153: keys of the data API. Behind DGATE_API_KEYS_OPEN on the API: closed, nothing can be made here. */
export default async function KeysPage({ searchParams }: Props) {
  const [result, { n }] = await Promise.all([listApiKeys(), searchParams]);
  const state = dataOrNull(result);
  if (!state) return <LoadFailed href="/app/keys" />;
  const now = Date.now();
  const active = state.keys.filter((k) => !k.revokedAt && Date.parse(k.expiresAt) > now);
  return (
    <>
      <AppHeader title="API keys" lead="Keys for your own scripts to read the data API. What it gives: the API page." />
      <Notice code={n} />

      <Block id="new" title="Make a key">
        {state.open ? (
          active.length >= state.maxKeys
            ? <p className="m-0 text-body text-ink-muted">This account holds {state.maxKeys} keys, the most it may. Revoke one to make another.</p>
            : <ApiKeyCreate />
        ) : (
          <p className="m-0 max-w-prose text-body text-ink-muted" data-keys-closed>API keys are not issued yet. The licence is on request: see <Link href="/api" className="font-semibold">the API page</Link>.</p>
        )}
      </Block>

      <Block id="keys" title="Your keys">
        {state.keys.length === 0 ? (
          <p className="m-0 text-body text-ink-muted">No keys yet.</p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {state.keys.map((k) => {
              const expired = Date.parse(k.expiresAt) <= now;
              return (
                <li key={k.id} className="flex flex-col gap-3 rounded-md bg-surface-inset p-4" data-key={k.prefix}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-body font-semibold [overflow-wrap:anywhere]">{k.name}</span>
                    <span className="font-mono text-mono text-ink-muted">dgk_{k.prefix}_…</span>
                    {k.revokedAt ? <Tag>Revoked</Tag> : expired ? <Tag>Expired</Tag> : null}
                  </div>
                  <p className="m-0 font-mono text-mono text-ink-muted [overflow-wrap:anywhere]">
                    {k.scopes.join(', ')} · {k.ratePerMinute} a minute, {k.dailyQuota.toLocaleString('en-GB')} a day · made {formatStamp(k.createdAt)} ·
                    {' '}{k.revokedAt ? `revoked ${formatStamp(k.revokedAt)}` : `expires ${formatStamp(k.expiresAt)}`} ·
                    {' '}{k.lastUsedAt ? `last used ${formatStamp(k.lastUsedAt)}` : 'never used'} · {k.requestsToday.toLocaleString('en-GB')} requests today
                  </p>
                  {!k.revokedAt && !expired && (
                    <form action={endApiKey} className="flex flex-wrap items-end gap-3">
                      <input type="hidden" name="id" value={k.id} />
                      <TextInput name="password" type="password" autoComplete="current-password" maxLength={1024} required label="Your password" className="max-w-form" />
                      <Button type="submit" variant="secondary">Revoke this key</Button>
                    </form>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Block>

      {state.events.length > 0 && (
        <Block id="history" title="History">
          <ul className="m-0 flex list-none flex-col gap-1 p-0 font-mono text-mono text-ink-muted">
            {state.events.map((e) => <li key={`${e.at}-${e.prefix}-${e.event}`}>{formatStamp(e.at)} · {e.event} · {e.name} (dgk_{e.prefix}_…)</li>)}
          </ul>
        </Block>
      )}

      <p className="m-0 text-small text-ink-muted">A key reads these sources: {state.sources.join(', ') || 'none'}. Requests with a key are counted per day; keys, their history and the counts are deleted with the account.</p>
    </>
  );
}
