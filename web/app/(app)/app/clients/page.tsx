import type { Metadata } from 'next';
import Link from 'next/link';
import { Trash2 } from 'lucide-react';
import { dataOrNull } from '@/lib/account';
import { activeClient, listClients, type ClientProfile } from '@/lib/workspace';
import { Button } from '@/components/dg/button';
import { Textarea, TextInput } from '@/components/dg/form';
import { Tag } from '@/components/dg/tag';
import { ClientSwitcher } from '@/components/account/client-switcher';
import { AppHeader, Block, LoadFailed, NextStep, Notice } from '@/components/account/ui';
import { addClient, chooseClient, removeClient, saveClient } from '../team/actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Clients', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[] }> };

const HINT = 'Commercial information only: the company, where it sells and under which CPV codes. No names of people, no contact details.';

function Fields({ c }: { c?: ClientProfile }) {
  return (
    <>
      <TextInput name="name" label="Company name" required maxLength={120} defaultValue={c?.name} />
      <div className="grid gap-4 sm:grid-cols-[120px_minmax(0,1fr)]">
        <TextInput name="country" label="Country" maxLength={2} defaultValue={c?.country ?? ''} hint="Two letters: DE, ES" />
        <TextInput name="cpv" label="CPV codes" maxLength={400} defaultValue={c?.cpvCodes.join(', ')} hint="2 to 8 digits each, separated by commas; at most 20" />
      </div>
      <Textarea name="note" label="Note (up to 500 characters)" maxLength={500} rows={3} defaultValue={c?.note ?? ''} className="min-w-0" />
    </>
  );
}

/** WP-157: a consultant's client profiles (Consultant). Saved searches and shortlist entries can belong to one; the switcher picks the one worked on. */
export default async function ClientsPage({ searchParams }: Props) {
  const [result, { n }] = await Promise.all([listClients(), searchParams]);
  const state = dataOrNull(result);
  if (!state) return <LoadFailed href="/app/clients" />;
  const active = await activeClient(state.items);
  return (
    <>
      <AppHeader title="Clients" lead="The companies you work for. Give a saved search or a shortlist entry to a client, pick the client you work on, and its name goes on its company reports." />
      <Notice code={n} />
      <ClientSwitcher clients={state.items} active={active} back="/app/clients" />

      {!state.allowed ? (
        <p className="m-0 max-w-prose text-body text-ink-muted" data-clients-plan>
          Client profiles are part of Consultant. See <Link href="/app/billing" className="font-semibold">Billing</Link>.{state.items.length > 0 && ' The profiles you made are kept below.'}
        </p>
      ) : state.items.length < state.limit ? (
        <Block id="new" title="Add a client" aside={<span className="font-mono text-mono text-ink-muted">{state.items.length} of {state.limit}</span>}>
          <form action={addClient} className="flex max-w-form flex-col gap-4" data-client-new>
            <p className="m-0 text-small text-ink-muted">{HINT}</p>
            <Fields />
            <div><Button type="submit">Add client</Button></div>
          </form>
        </Block>
      ) : (
        <p className="m-0 text-body text-ink-muted">You hold {state.limit} client profiles, the most your plan has. Remove one to add another.</p>
      )}

      {state.items.length === 0 ? (
        state.allowed && <NextStep links={[{ label: 'Open tenders', href: '/tenders' }]}>No clients yet. Add the first above; then save searches and shortlist notices for it.</NextStep>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {state.items.map((c) => (
            <li key={c.id} className="flex flex-col gap-4 rounded-lg border border-transparent bg-surface p-5 sm:p-7" data-client={c.name}>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="m-0 min-w-0 break-words text-h3">{c.name}</h2>
                {c.country && <Tag>{c.country}</Tag>}
                {active?.id === c.id && <Tag kind="programme">Working on</Tag>}
              </div>
              {state.allowed && (
                <form action={saveClient} className="flex max-w-form flex-col gap-4">
                  <input type="hidden" name="id" value={c.id} />
                  <Fields c={c} />
                  <div><Button type="submit" variant="secondary">Save changes</Button></div>
                </form>
              )}
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                {active?.id !== c.id && (
                  <form action={chooseClient}>
                    <input type="hidden" name="clientId" value={c.id} />
                    <input type="hidden" name="back" value="/app/clients" />
                    <Button type="submit" variant="text">Work on this client</Button>
                  </form>
                )}
                <form action={removeClient}>
                  <input type="hidden" name="id" value={c.id} />
                  <Button type="submit" variant="text" icon={Trash2} aria-label={`Remove client ${c.name}`}>Remove</Button>
                </form>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
