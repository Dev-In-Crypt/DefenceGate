import type { Metadata } from 'next';
import Link from 'next/link';
import { Download } from 'lucide-react';
import { ApiError, getSignal } from '@/lib/api';
import { getFullSignal, readSession } from '@/lib/account';
import { formatDateUtc, formatNumber, plural } from '@/lib/format';
import { countryName } from '@/lib/taxonomy';
import { parseCountries } from '@/lib/country-input';
import { displayName } from '@/lib/display-name';
import { buildMetadata } from '@/lib/seo';
import type { SearchParams } from '@/lib/filters';
import {
  FULL_PAGE_SIZE, KIND_TITLE, NOT_ADVICE, SIGNAL_KINDS, SIGNAL_PROGRAMMES, comparableLine, fullState, kindLine, parseSignalFilters, signalHref,
  type FundingRow, type GrowingRow, type MarketRow, type SignalAnswer, type SignalFilters, type SignalNotice,
} from '@/lib/signals';
import { PageHeader } from '@/components/dg/page-header';
import { NoteLine } from '@/components/dg/blocks';
import { EmptyState } from '@/components/dg/feedback';
import { Button } from '@/components/dg/button';
import { CountryLabel } from '@/components/dg/data-display';
import { Pagination } from '@/components/dg/pagination';
import { Select, TextInput } from '@/components/dg/form';
import { Tag } from '@/components/dg/tag';
import { Icon } from '@/components/dg/icon';
import { AboutData } from '@/components/dg/about-data';
import { cn } from '@/lib/utils';

// The paid part reads the visitor's session (lib/account.ts), so the page is rendered per request.
export const dynamic = 'force-dynamic';

type Props = { searchParams: Promise<SearchParams> };

const LEAD = 'Which companies are winning more defence contracts, entering new markets or newly funded by the EU, from public award notices and EU project records.';

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseSignalFilters(await searchParams);
  const filtered = Boolean(f.country || f.cpv || f.programme || f.page > 1 || f.kind !== 'growing');
  return buildMetadata({ title: filtered ? `Company signals: ${KIND_TITLE[f.kind]}` : 'Company signals', description: LEAD, path: '/signals', noindex: filtered });
}

const day = (iso: string) => formatDateUtc(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
const LINK = 'inline-flex min-h-11 items-center gap-2 text-small font-bold';

function Source({ n, label }: { n: SignalNotice; label: string }) {
  return (
    <span>
      {label}{' '}
      {n.sourceUrl ? <a href={n.sourceUrl} rel="noopener" className="font-mono">{n.noticeId}</a> : n.noticeId}
      {' '}({n.source === 'ted' ? 'TED' : n.source.toUpperCase()}{n.publishedAt ? `, ${formatDateUtc(n.publishedAt)}` : ''}),{' '}
      <Link href={`/tenders/${n.slug}`}>our copy</Link>
    </span>
  );
}

const ROW = 'flex min-w-0 flex-col gap-1 rounded-lg border border-transparent bg-surface p-4';
const FACTS = 'flex flex-wrap items-baseline gap-x-4 gap-y-1 text-small text-ink-muted';

function Company({ c, href }: { c: GrowingRow['company']; href: string }) {
  return <Link href={href} className="inline-flex min-h-8 items-center break-words text-h3 font-semibold">{displayName(c.name, 'title')}</Link>;
}

function GrowingItem({ r }: { r: GrowingRow }) {
  const values = comparableLine(r);
  return (
    <li className={ROW} data-signal-row>
      <Company c={r.company} href={`/suppliers/${r.company.slug}`} />
      <span className={FACTS}>
        {r.company.country && <CountryLabel code={r.company.country} />}
        <span className="text-ink" data-counts>{formatNumber(r.recent)} awarded {plural(r.recent, 'procurement')} in the last 12 months, {formatNumber(r.prior)} in the 12 before</span>
      </span>
      <span className="text-small text-ink">{values ? `Contract values: ${values}` : 'No contract values in one currency in both periods.'}</span>
      {r.latest && <span className="text-small text-ink-muted"><Source n={r.latest} label="Latest:" /></span>}
    </li>
  );
}

function MarketItem({ r }: { r: MarketRow }) {
  return (
    <li className={ROW} data-signal-row>
      <Company c={r.company} href={`/suppliers/${r.company.slug}`} />
      <span className={FACTS}>
        {r.company.country && <CountryLabel code={r.company.country} />}
        <span className="text-ink" data-counts>
          First win with a buyer in {countryName(r.market)}{r.firstWinAt ? ` on ${formatDateUtc(r.firstWinAt)}` : ''}; {formatNumber(r.winsThere)} {plural(r.winsThere, 'win')} there since,
          {' '}{formatNumber(r.winsBefore)} elsewhere before
        </span>
      </span>
      {r.firstWin && <span className="text-small text-ink-muted"><Source n={r.firstWin} label="First win:" /></span>}
    </li>
  );
}

function FundingItem({ r }: { r: FundingRow }) {
  return (
    <li className={ROW} data-signal-row>
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Company c={r.company} href={`/organisations/${r.company.slug}`} />
        {r.first && <Tag>First EU defence project</Tag>}
      </span>
      <span className={FACTS}>
        {r.company.country && <CountryLabel code={r.company.country} />}
        <span className="text-ink" data-counts>
          {formatNumber(r.newProjects)} {plural(r.newProjects, 'project')} of the {r.year} calls{r.first ? '' : `, ${formatNumber(r.earlierProjects)} earlier`}
        </span>
      </span>
      <span className="text-small text-ink-muted">
        {r.projects.map((p, i) => (
          <span key={p.slug}>{i > 0 ? ', ' : ''}<Link href={`/projects/${p.slug}`}>{p.acronym ?? p.title}</Link> ({p.programme}, {p.role.replace(/_/g, ' ')})</span>
        ))}
        {r.newProjects > r.projects.length ? ` and ${r.newProjects - r.projects.length} more` : ''}
      </span>
    </li>
  );
}

function Filters({ f }: { f: SignalFilters }) {
  return (
    <form method="get" action="/signals" aria-label="Filter the signal" className="flex flex-wrap items-end gap-3">
      {f.kind !== 'growing' && <input type="hidden" name="kind" value={f.kind} />}
      <TextInput name="country" label="Company country" defaultValue={f.country} maxLength={60} placeholder="For example DE or Germany" className="w-full sm:w-64" />
      {f.kind === 'funding'
        ? <Select name="programme" label="Programme" defaultValue={f.programme} className="w-full sm:w-56"
            options={[{ value: '', label: 'Every defence programme' }, ...SIGNAL_PROGRAMMES.map((p) => ({ value: p, label: p }))]} />
        : <TextInput name="cpv" label="CPV code or its start" defaultValue={f.cpv} maxLength={40} inputMode="numeric" placeholder="For example 3540" className="w-full sm:w-56" />}
      <Button type="submit" variant="secondary">Apply</Button>
    </form>
  );
}

/** What the visitor gets beyond the first rows: nothing while the paid part is closed, else the way to it or the list itself. */
function FullLine({ state, a, f }: { state: ReturnType<typeof fullState>; a: SignalAnswer; f: SignalFilters }) {
  const shownTo = a.offset + a.items.length;
  const counted = `${a.total > a.items.length ? `${formatNumber(a.offset + 1)} to ${formatNumber(shownTo)} of` : 'All'} ${formatNumber(a.total)} ${plural(a.total, 'company', 'companies')}.`;
  if (state === 'full') {
    return (
      <div className="flex flex-wrap items-center gap-x-5 text-small text-ink-muted" data-full>
        <span>{counted}</span>
        <a href={signalHref(f, { page: 1 }, '/signals/export.csv')} className={LINK}><Icon icon={Download} size="inline" />Download CSV</a>
      </div>
    );
  }
  const first = a.total > a.items.length ? `The first ${formatNumber(a.items.length)} of ${formatNumber(a.total)} ${plural(a.total, 'company', 'companies')}.` : counted;
  return (
    <p className="m-0 text-small text-ink-muted" data-full-state={state}>
      {first}
      {state === 'signin' && a.total > a.items.length && <> The full list and its CSV are part of a paid plan: <Link href="/signin?next=/signals">sign in</Link> or see <Link href="/pricing">pricing</Link>.</>}
      {state === 'plan' && a.total > a.items.length && <> The full list and its CSV are part of a paid plan: <Link href="/app/billing">choose one under Billing</Link>.</>}
    </p>
  );
}

export default async function SignalsPage({ searchParams }: Props) {
  const f = parseSignalFilters(await searchParams);
  const { codes, unknown } = parseCountries(f.country);
  const api = { kind: f.kind, country: codes.join(','), cpv: f.cpv, programme: f.programme };
  let a: SignalAnswer | null = null;
  let refused = unknown.length > 0;
  if (!refused) {
    try {
      a = await getSignal(api);
    } catch (e) {
      // a CPV start the API cannot read (2 to 8 digits) is an answer to the form, never an error page
      if (!(e instanceof ApiError && e.status === 422)) throw e;
      refused = true;
    }
  }
  // The paid part: asked only when it is open and the visitor has a session; the public answer says whether it is open.
  let state = fullState(Boolean(a?.fullOpen), 0);
  if (a && a.fullOpen && await readSession()) {
    const full = await getFullSignal(api, f.page, FULL_PAGE_SIZE);
    state = fullState(true, full.ok ? 200 : full.status);
    if (full.ok) a = full.data;
  }
  const latestYear = a?.kind === 'funding' ? (a.items[0] as FundingRow | undefined)?.year : null;
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', href: '/' }, { label: 'Company signals', href: '/signals' }]} title="Company signals" lead={LEAD} />
      <section className="flex min-w-0 flex-col gap-4">
        <nav aria-label="Signals" className="flex flex-wrap gap-2 border-b border-line">
          {SIGNAL_KINDS.map((k) => (
            <Link key={k} href={signalHref({ kind: k, country: f.country, cpv: '', programme: '', page: 1 })} aria-current={k === f.kind ? 'page' : undefined}
              className={cn('-mb-px inline-flex min-h-11 items-center border-b-[3px] px-3 text-body font-bold no-underline',
                k === f.kind ? 'border-accent-text text-ink' : 'border-transparent text-ink-muted hover:text-ink')}>
              {KIND_TITLE[k]}
            </Link>
          ))}
        </nav>
        <Filters f={f} />
        {a && <p className="m-0 max-w-prose text-small text-ink" data-kind-line>{kindLine(a, day, latestYear)}</p>}
        {refused || !a ? (
          <EmptyState title={unknown.length > 0 ? 'Not a country' : 'These filters cannot be read'} action={<Button variant="secondary" href={signalHref({ ...f, country: '', cpv: '', programme: '', page: 1 })}>Clear filters</Button>}>
            {unknown.length > 0
              ? `“${unknown.join(', ')}” is not a country code or an English country name. Use a code such as DE or DEU, or a name such as Germany.`
              : 'A CPV code or its start has 2 to 8 digits, for example 35 or 3540.'}
          </EmptyState>
        ) : a.items.length === 0 ? (
          <EmptyState title="No company matches" action={<Button variant="secondary" href={signalHref({ ...f, country: '', cpv: '', programme: '', page: 1 })}>Clear filters</Button>}>
            Fewer filters may find some: every row is a fact from the award notices or the EU project records we hold.
          </EmptyState>
        ) : (
          <>
            <ul className="m-0 flex list-none flex-col gap-3 p-0" data-signal-list={a.kind}>
              {a.kind === 'growing' && (a.items as GrowingRow[]).map((r) => <GrowingItem key={r.company.id} r={r} />)}
              {a.kind === 'markets' && (a.items as MarketRow[]).map((r) => <MarketItem key={`${r.company.id}-${r.market}`} r={r} />)}
              {a.kind === 'funding' && (a.items as FundingRow[]).map((r) => <FundingItem key={r.company.id} r={r} />)}
            </ul>
            <FullLine state={state} a={a} f={f} />
            {state === 'full' && <Pagination page={f.page} total={a.total} pageSize={FULL_PAGE_SIZE} hrefFor={(p) => signalHref(f, { page: p })} />}
          </>
        )}
        <NoteLine data-not-advice more={<AboutData summary="How we count">
          A procurement is counted once however many notices publish it, in the period of its newest notice, as on each company&rsquo;s page.
          Winners are the companies named in TED result notices{a?.sources.some((s) => s.code === 'es_placsp') ? ' and in the award results of Spain’s national portal' : ''} of the
          defence-relevant scope over the last three years; contract values are summed per currency, never converted, and a value under
          EUR 1,000 that reads as a unit price is in no sum. New markets count the buyer&rsquo;s country. EU defence funding counts active
          participations in projects of the European Defence Fund, EDIDP, EDIP and PADR. Natural persons are never named. These are facts
          from public records; they say nothing about a company&rsquo;s prospects.
        </AboutData>}>{NOT_ADVICE}</NoteLine>
        {a && <p className="m-0 max-w-prose text-small text-ink-muted" data-attribution>{a.sources.map((s) => s.attribution ?? s.name).join(' ')}</p>}
      </section>
    </>
  );
}
