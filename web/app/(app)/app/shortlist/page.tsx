import type { Metadata } from 'next';
import { Trash2 } from 'lucide-react';
import { dataOrNull, getCurrentUser, listShortlist } from '@/lib/account';
import { STATUS_LABEL, STATUS_ORDER } from '@/lib/account-format';
import type { ShortlistItem, ShortlistStatus } from '@/lib/types';
import { clientContext, type ClientProfile } from '@/lib/workspace';
import { Button } from '@/components/dg/button';
import { Select, Textarea } from '@/components/dg/form';
import { Tag } from '@/components/dg/tag';
import { ClientSwitcher } from '@/components/account/client-switcher';
import { AppHeader, ItemRow, LoadFailed, NextStep, Notice } from '@/components/account/ui';
import { removeShortlistItem, saveShortlistItem } from '../actions';
import { saveShortlistWithClient } from '../team/actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Shortlist', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[] }> };

const STATUS_OPTIONS = STATUS_ORDER.map((s) => ({ value: s, label: STATUS_LABEL[s] }));

function Item({ s, shared, clients }: { s: ShortlistItem; shared: boolean; clients: ClientProfile[] }) {
  const client = clients.find((c) => c.id === s.clientId);
  return (
    <li className="flex flex-col gap-4 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
      <ul className="m-0 list-none p-0"><ItemRow kind={s.kind} item={s.item} refId={s.ref} badge={client ? <Tag wrap>{client.name}</Tag> : undefined} /></ul>
      {/* WP-157: with client profiles the same form also gives the entry to a client (its own action, so the plain one is unchanged) */}
      <form action={clients.length > 0 ? saveShortlistWithClient : saveShortlistItem} className="flex flex-col gap-3">
        <input type="hidden" name="kind" value={s.kind} />
        <input type="hidden" name="ref" value={s.ref} />
        <div className="grid items-start gap-3 sm:grid-cols-[200px_minmax(0,1fr)]">
          <div className="flex flex-col gap-3">
            <Select name="status" label="Status" options={STATUS_OPTIONS} defaultValue={s.status} />
            {clients.length > 0 && (
              <Select name="clientId" label="Client" defaultValue={s.clientId ?? ''}
                options={[{ value: '', label: 'No client' }, ...clients.map((c) => ({ value: c.id, label: c.name }))]} />
            )}
          </div>
          <Textarea name="note" label={shared ? 'Note (seen by your team, up to 500 characters)' : 'Note (private, up to 500 characters)'} maxLength={500} rows={3} defaultValue={s.note ?? ''} className="min-w-0" />
        </div>
        <div><Button type="submit" variant="secondary">Save changes</Button></div>
      </form>
      <form action={removeShortlistItem}>
        <input type="hidden" name="kind" value={s.kind} />
        <input type="hidden" name="ref" value={s.ref} />
        <Button type="submit" variant="text" icon={Trash2}>Remove from shortlist</Button>
      </form>
    </li>
  );
}

export default async function ShortlistPage({ searchParams }: Props) {
  const [me, { n }] = await Promise.all([getCurrentUser(), searchParams]);
  const { clients, active } = await clientContext(me?.features ?? []);
  const items = dataOrNull(await listShortlist(active?.id));
  const shared = me?.workspace?.active === true;
  const groups = items === null ? [] : STATUS_ORDER
    .map((status) => ({
      status,
      items: items.filter((i) => (STATUS_ORDER.includes(i.status) ? i.status : ('watching' as ShortlistStatus)) === status),
    }))
    .filter((g) => g.items.length > 0);
  return (
    <>
      <AppHeader title="Shortlist" lead={shared
        ? 'Notices and calls your team is tracking, grouped by where they stand. Statuses and notes are shared with your team.'
        : 'Notices and calls you are tracking, grouped by where they stand. Notes are visible to you only.'} />
      <Notice code={n} />
      <ClientSwitcher clients={clients} active={active} back="/app/shortlist" />
      {active && <p className="m-0 text-small text-ink-muted" data-client-filter>The shortlist of {active.name}.</p>}
      {items === null ? <LoadFailed href="/app/shortlist" /> : groups.length === 0 ? (
        <NextStep links={[{ label: 'Open tenders', href: '/tenders' }, { label: 'Open funding calls', href: '/funding' }]}>
          Your shortlist is empty. Open a tender or a funding call and choose Shortlist to track it here.
        </NextStep>
      ) : groups.map((g) => (
        <section key={g.status} aria-labelledby={`g-${g.status}`} className="flex flex-col gap-4">
          <h2 id={`g-${g.status}`} className="m-0 text-h2">
            {STATUS_LABEL[g.status]} <span className="font-mono text-mono-strong text-ink-muted">{g.items.length}</span>
          </h2>
          <ul className="m-0 flex list-none flex-col gap-4 p-0">
            {g.items.map((s) => <Item key={`${s.kind}/${s.ref}`} s={s} shared={shared} clients={clients} />)}
          </ul>
        </section>
      ))}
    </>
  );
}
