import type { Metadata } from 'next';
import { Trash2 } from 'lucide-react';
import { dataOrNull, listShortlist } from '@/lib/account';
import { STATUS_LABEL, STATUS_ORDER } from '@/lib/account-format';
import type { ShortlistItem, ShortlistStatus } from '@/lib/types';
import { Button } from '@/components/dg/button';
import { Select, Textarea } from '@/components/dg/form';
import { AppHeader, ItemRow, LoadFailed, NextStep, Notice } from '@/components/account/ui';
import { removeShortlistItem, saveShortlistItem } from '../actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Shortlist', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[] }> };

const STATUS_OPTIONS = STATUS_ORDER.map((s) => ({ value: s, label: STATUS_LABEL[s] }));

function Item({ s }: { s: ShortlistItem }) {
  return (
    <li className="flex flex-col gap-4 rounded-lg bg-surface p-5 sm:p-6">
      <ul className="m-0 list-none p-0"><ItemRow kind={s.kind} item={s.item} refId={s.ref} /></ul>
      <form action={saveShortlistItem} className="flex flex-col gap-3">
        <input type="hidden" name="kind" value={s.kind} />
        <input type="hidden" name="ref" value={s.ref} />
        <div className="grid items-start gap-3 sm:grid-cols-[200px_minmax(0,1fr)]">
          <Select name="status" label="Status" options={STATUS_OPTIONS} defaultValue={s.status} />
          <Textarea name="note" label="Note (private, up to 500 characters)" maxLength={500} rows={3} defaultValue={s.note ?? ''} className="min-w-0" />
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
  const [result, { n }] = await Promise.all([listShortlist(), searchParams]);
  const items = dataOrNull(result);
  const groups = items === null ? [] : STATUS_ORDER
    .map((status) => ({
      status,
      items: items.filter((i) => (STATUS_ORDER.includes(i.status) ? i.status : ('watching' as ShortlistStatus)) === status),
    }))
    .filter((g) => g.items.length > 0);
  return (
    <>
      <AppHeader title="Shortlist" lead="Notices and calls you are tracking, grouped by where they stand. Notes are visible to you only." />
      <Notice code={n} />
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
            {g.items.map((s) => <Item key={`${s.kind}/${s.ref}`} s={s} />)}
          </ul>
        </section>
      ))}
    </>
  );
}
