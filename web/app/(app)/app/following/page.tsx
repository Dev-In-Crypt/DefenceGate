import type { Metadata } from 'next';
import Link from 'next/link';
import { BellOff } from 'lucide-react';
import { dataOrNull, listFollows } from '@/lib/account';
import { followHref } from '@/lib/account-format';
import { formatDateUtc, formatNumber } from '@/lib/format';
import type { Buyer, Follow } from '@/lib/types';
import { Button } from '@/components/dg/button';
import { Tag } from '@/components/dg/tag';
import { AppHeader, LoadFailed, NextStep, Notice } from '@/components/account/ui';
import { unfollow } from '../actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Following', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[] }> };

function describe(f: Follow): { name: string; open: number | null; slug: string | null; latest: string | null } {
  if (!f.item) return { name: f.ref, open: null, slug: null, latest: null };
  if (f.kind === 'buyer') {
    const b = f.item as Buyer;
    return { name: b.name, open: b.openCount, slug: b.slug, latest: b.lastPublishedAt };
  }
  const p = f.item as { name: string; openCount: number };
  return { name: p.name, open: p.openCount, slug: null, latest: null };
}

export default async function FollowingPage({ searchParams }: Props) {
  const [result, { n }] = await Promise.all([listFollows(), searchParams]);
  const follows = dataOrNull(result);
  return (
    <>
      <AppHeader title="Following" lead="Buyers and programmes you follow. Changes to the notices of the buyers you follow appear on your dashboard; the calls of a programme are counted, not tracked for changes." />
      <Notice code={n} />
      {follows === null ? <LoadFailed href="/app/following" /> : follows.length === 0 ? (
        <NextStep links={[{ label: 'Browse buyers', href: '/buyers' }, { label: 'Browse funding calls', href: '/funding' }]}>
          You follow nothing yet. Open a buyer, or a funding call, and choose Follow.
        </NextStep>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {follows.map((f) => {
            const d = describe(f);
            const href = followHref(f.kind, f.ref, d.slug);
            return (
              <li key={`${f.kind}/${f.ref}`} className="flex flex-col gap-3 rounded-lg border border-edge bg-surface p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
                <div className="flex min-w-0 flex-col gap-2">
                  <div><Tag>{f.kind === 'buyer' ? 'Buyer' : 'Programme'}</Tag></div>
                  <h2 className="m-0 break-words text-h3">
                    {href ? <Link href={href} className="text-ink">{d.name}</Link> : d.name}
                  </h2>
                  <p className="m-0 font-mono text-mono text-ink-muted">
                    {d.open === null ? 'No longer available' : `${formatNumber(d.open)} open`}
                    {d.latest ? ` · latest ${formatDateUtc(d.latest)}` : ''}
                  </p>
                </div>
                <form action={unfollow}>
                  <input type="hidden" name="kind" value={f.kind} />
                  <input type="hidden" name="ref" value={f.ref} />
                  <Button type="submit" variant="secondary" icon={BellOff} aria-label={`Unfollow ${d.name}`}>Unfollow</Button>
                </form>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
