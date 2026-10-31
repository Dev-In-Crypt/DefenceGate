import type { Metadata } from 'next';
import Link from 'next/link';
import { Download } from 'lucide-react';
import { ApiError, getEnding } from '@/lib/api';
import { getFullEnding, readSession } from '@/lib/account';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { countryName } from '@/lib/taxonomy';
import { parseCountries } from '@/lib/country-input';
import { buildMetadata } from '@/lib/seo';
import type { SearchParams } from '@/lib/filters';
import {
  FULL_PAGE_SIZE, WHY, WITHIN, coverageLine, endingHref, endingState, parseEndingFilters,
  type EndingAnswer, type EndingFilters, type EndingState,
} from '@/lib/contract-period';
import { PageHeader } from '@/components/dg/page-header';
import { EmptyState } from '@/components/dg/feedback';
import { Button } from '@/components/dg/button';
import { Pagination } from '@/components/dg/pagination';
import { TextInput } from '@/components/dg/form';
import { Icon } from '@/components/dg/icon';
import { AboutData } from '@/components/dg/about-data';
import { NoteLine } from '@/components/dg/blocks';
import { SaveSearch } from '@/components/account/save-search';
import { EndingRow } from '@/components/tenders/contract-period';
import { cn } from '@/lib/utils';

// The paid part reads the visitor's session (lib/account.ts), so the page is rendered per request.
export const dynamic = 'force-dynamic';

type Props = { searchParams: Promise<SearchParams> };

const TITLE = 'Contracts ending soon';
const LEAD = 'Defence contracts whose period ends in the next 3, 6 or 12 months, from the contract periods the notices state.';
const LINK = 'inline-flex min-h-11 items-center gap-2 text-small font-bold';

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseEndingFilters(await searchParams);
  const filtered = Boolean(f.country || f.cpv || f.buyer || f.estimated || f.page > 1 || f.within !== 12);
  return buildMetadata({ title: TITLE, description: LEAD, path: '/tenders/ending', noindex: filtered });
}

function Filters({ f }: { f: EndingFilters }) {
  return (
    <form method="get" action="/tenders/ending" aria-label="Filter the contracts ending soon" className="flex flex-col gap-3">
      {f.buyer && <input type="hidden" name="buyer" value={f.buyer} />}
      <fieldset className="m-0 flex flex-wrap gap-2 border-0 p-0">
        <legend className="mb-2 text-label text-ink-muted">Ends within</legend>
        {WITHIN.map((w) => (
          <label key={w} className={cn('inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-md border px-3 text-body',
            w === f.within ? 'border-accent-text font-bold text-ink' : 'border-line text-ink-muted')}>
            <input type="radio" name="within" value={w} defaultChecked={w === f.within} className="h-4 w-4" />
            {w} months
          </label>
        ))}
      </fieldset>
      <div className="flex flex-wrap items-end gap-3">
        <TextInput name="country" label="Buyer country" defaultValue={f.country} maxLength={60} placeholder="For example DE or Germany" className="w-full sm:w-64" />
        <TextInput name="cpv" label="CPV code or its start" defaultValue={f.cpv} maxLength={40} inputMode="numeric" placeholder="For example 3541" className="w-full sm:w-56" />
        <label className="inline-flex min-h-11 items-center gap-2 text-body text-ink">
          <input type="checkbox" name="estimated" value="true" defaultChecked={f.estimated} className="h-4 w-4" />
          Include estimated end dates
        </label>
        <Button type="submit" variant="secondary">Apply</Button>
      </div>
    </form>
  );
}

/** Beyond the first rows: sign in, a plan, or the full list with its CSV (Team). */
function FullLine({ state, a, f }: { state: EndingState; a: EndingAnswer; f: EndingFilters }) {
  const n = (x: number) => formatNumber(x);
  if (state === 'full') {
    const shown = a.offset + a.items.length;
    return (
      <div className="flex flex-wrap items-center gap-x-5 text-small text-ink-muted" data-full>
        <span>{a.total > a.items.length ? `${n(a.offset + 1)} to ${n(shown)} of` : 'All'} {n(a.total)} {a.total === 1 ? 'contract' : 'contracts'}.</span>
        {a.csv
          ? <a href={endingHref(f, { page: 1 }, '/tenders/ending/export.csv')} className={LINK}><Icon icon={Download} size="inline" />Download CSV</a>
          : <span data-csv-plan>The CSV is part of the Team and Consultant plans: <Link href="/app/billing">Billing</Link>.</span>}
      </div>
    );
  }
  const more = a.total > a.items.length;
  return (
    <p className="m-0 text-small text-ink-muted" data-full-state={state}>
      <span data-first-rows>{more ? `The first ${n(a.items.length)} of ${n(a.total)} contracts.` : `All ${n(a.total)} ${a.total === 1 ? 'contract' : 'contracts'}.`}</span>
      {state === 'signin' && more && <> The full list, its alerts and the CSV are part of a paid plan: <Link href="/signin?next=/tenders/ending">sign in</Link> or see <Link href="/pricing">pricing</Link>.</>}
      {state === 'plan' && more && <> The full list and its alerts are part of Pro: <Link href="/app/billing">choose a plan under Billing</Link>.</>}
    </p>
  );
}

export default async function EndingPage({ searchParams }: Props) {
  const f = parseEndingFilters(await searchParams);
  const { codes, unknown } = parseCountries(f.country);
  const api = { within: f.within, country: codes.join(','), cpv: f.cpv, buyer: f.buyer, estimated: f.estimated };
  let a: EndingAnswer | null = null;
  let refused = unknown.length > 0;
  if (!refused) {
    try {
      a = await getEnding(api);
    } catch (e) {
      // a CPV start the API cannot read is an answer to the form, never an error page
      if (!(e instanceof ApiError && e.status === 422)) throw e;
      refused = true;
    }
  }
  let state: EndingState = 'signin';
  if (a && await readSession()) {
    const full = await getFullEnding(api, f.page, FULL_PAGE_SIZE);
    state = endingState(full.ok ? 200 : full.status);
    if (full.ok) a = full.data;
  }
  const clear = endingHref({ ...f, country: '', cpv: '', buyer: '', estimated: false, page: 1 });
  const day = (iso: string) => formatDateUtc(`${iso}T00:00:00Z`);
  const saved: Record<string, string> = { within: String(f.within) };
  for (const [k, v] of Object.entries({ country: api.country, cpv: f.cpv, buyer: f.buyer, estimated: f.estimated ? 'true' : '' })) if (v) saved[k] = v;

  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', href: '/' }, { label: 'Tenders', href: '/tenders' }, { label: TITLE, href: '/tenders/ending' }]} title={TITLE} lead={LEAD} />
      <section className="flex min-w-0 flex-col gap-4">
        <p className="m-0 max-w-prose text-body text-ink" data-why>{WHY}</p>
        <Filters f={f} />
        {a && <p className="m-0 text-small text-ink-muted" data-window>Ending between {day(a.from)} and {day(a.to)}; soonest first. Each row says where its end date comes from.</p>}
        {refused || !a ? (
          <EmptyState title={unknown.length > 0 ? 'Not a country' : 'These filters cannot be read'} action={<Button variant="secondary" href={clear}>Clear filters</Button>}>
            {unknown.length > 0
              ? `“${unknown.join(', ')}” is not a country code or an English country name. Use a code such as DE or DEU, or a name such as Germany.`
              : 'A CPV code or its start has 2 to 8 digits, for example 35 or 3541.'}
          </EmptyState>
        ) : a.items.length === 0 ? (
          <EmptyState title="No contract ends in this window" action={<Button variant="secondary" href={clear}>Clear filters</Button>}>
            A longer window or fewer filters may find some. Only notices that state a contract period can be listed here.
          </EmptyState>
        ) : (
          <>
            <ul className="m-0 flex list-none flex-col gap-3 p-0" data-ending-list>
              {a.items.map((t) => <EndingRow key={t.id} t={t} />)}
            </ul>
            <FullLine state={state} a={a} f={f} />
            {state === 'full' && <Pagination page={f.page} total={a.total} pageSize={FULL_PAGE_SIZE} hrefFor={(p) => endingHref(f, { page: p })} />}
          </>
        )}
        {a && <div className="max-w-sm"><SaveSearch kind="ending" filters={saved} /></div>}
        <NoteLine data-coverage more={<AboutData summary="Where the end dates come from">
          A stated end date is the one the notice gives. A computed one is the start date the notice states plus the duration it states.
          An estimated one, shown only when you ask for it, is an award notice that states a duration and no start: its publication date plus
          the duration, since a contract usually starts near its award. A notice that states a duration and no start, and is not an award, has
          no end date here. Renewal options are shown apart and never added to the end. A contract published in several notices (its call and
          its award, a national notice and its TED copy) is listed once. Check the notice before you act on a date.
        </AboutData>}>{a ? coverageLine(a.coverage, countryName) : ''}</NoteLine>
      </section>
    </>
  );
}
