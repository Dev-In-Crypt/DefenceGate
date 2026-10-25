import type { Metadata } from 'next';
import Link from 'next/link';
import { Trash2 } from 'lucide-react';
import { dataOrNull, listSearches } from '@/lib/account';
import { CADENCE_LABEL, KIND_LABEL, describeFilters, searchHref } from '@/lib/account-format';
import { formatDateUtc, formatNumber, plural } from '@/lib/format';
import type { Cadence } from '@/lib/types';
import { Button } from '@/components/dg/button';
import { Select } from '@/components/dg/form';
import { Tag } from '@/components/dg/tag';
import { AppHeader, LoadFailed, NextStep, Notice } from '@/components/account/ui';
import { removeSearch, setSearchCadence } from '../actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Saved searches', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[] }> };

const CADENCE_OPTIONS = (Object.keys(CADENCE_LABEL) as Cadence[]).map((c) => ({ value: c, label: CADENCE_LABEL[c] }));

export default async function SearchesPage({ searchParams }: Props) {
  const [result, { n }] = await Promise.all([listSearches(), searchParams]);
  const searches = dataOrNull(result);
  return (
    <>
      <AppHeader title="Saved searches" lead="A search is a set of filters you saved from the tenders or funding list. New matches show on your dashboard." />
      <Notice code={n} />
      {searches === null ? <LoadFailed href="/app/searches" /> : searches.length === 0 ? (
        <NextStep links={[{ label: 'Open tenders', href: '/tenders' }, { label: 'Open funding calls', href: '/funding' }]}>
          No saved searches yet. Set the filters you care about on the tenders or funding list, then choose Save this search.
        </NextStep>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {searches.map((s) => (
            <li key={s.id} className="flex flex-col gap-4 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
              <div className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Tag>{KIND_LABEL[s.kind] ?? s.kind}</Tag>
                  {s.newCount > 0 && <Tag kind="programme">{formatNumber(s.newCount)} new</Tag>}
                </div>
                <h2 className="m-0 break-words text-h3">{s.name}</h2>
                <ul className="m-0 flex list-none flex-wrap gap-x-3 gap-y-1 p-0 text-small text-ink-muted">
                  {describeFilters(s.kind, s.filters ?? {}).map((d) => <li key={d}>{d}</li>)}
                </ul>
                {s.paused || s.matchCount === null ? (
                  <p className="m-0 text-small text-ink-muted" data-paused>
                    Paused: your plan has no saved searches or alerts. The search is kept; it runs again with a plan that has them (<Link href="/app/billing" className="font-semibold">Billing</Link>).
                  </p>
                ) : (
                  <p className="m-0 font-mono text-mono text-ink-muted">
                    {formatNumber(s.matchCount)} {plural(s.matchCount, 'match', 'matches')} · {formatNumber(s.newCount)} new since your last visit
                    {s.lastMatchAt ? ` · latest ${formatDateUtc(s.lastMatchAt)}` : ''}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
                <form action={setSearchCadence} className="flex flex-wrap items-end gap-3">
                  <input type="hidden" name="id" value={s.id} />
                  <Select name="cadence" label="Alerts" options={CADENCE_OPTIONS} defaultValue={s.cadence} className="min-w-44" />
                  <Button type="submit" variant="secondary">Save</Button>
                </form>
                <Link href={searchHref(s.kind, s.filters ?? {})} className="inline-flex min-h-11 items-center text-small font-bold">Open results</Link>
                <form action={removeSearch}>
                  <input type="hidden" name="id" value={s.id} />
                  <Button type="submit" variant="text" icon={Trash2} aria-label={`Delete search ${s.name}`}>Delete</Button>
                </form>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
