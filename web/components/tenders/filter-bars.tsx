import Link from 'next/link';
import { Button } from '../dg/button';
import { Choice, FoldGroup, Select, TextInput } from '../dg/form';
import { FORM_BUTTONS } from '../funding/filter-bar';
import { FilterPanel } from '../funding/filter-panel';
import { BUYER_COUNTRIES, CURRENCIES, SCOPE_CHOICES } from '@/lib/taxonomy';
import {
  DEFAULT_CURRENCY, DEFAULT_TENDER_SCOPE, DEFAULT_TENDER_STATUS, MAX_QUERY_LENGTH, PARAM, activeBuyerFilterCount, activeTenderFilterCount,
  defaultTenderSort,
} from '@/lib/filters';
import { countsAsOf, overlapNote, scopeCountText } from '@/lib/list-count';
import type { BuyerFilters, ScopeCounts, TenderFilters, TenderScopeFilter, TenderStatusFilter } from '@/lib/types';

const STATUS_OPTIONS: { value: TenderStatusFilter; label: string }[] = [
  { value: 'open', label: 'Open' }, { value: 'planned', label: 'Planned' }, { value: 'closed', label: 'Closed' }, { value: 'all', label: 'All' },
];
/** The scope choices, in the order of the glossary (lib/taxonomy.ts SCOPE_CHOICES); `all` is the escape hatch. */
const SCOPE_OPTIONS: TenderScopeFilter[] = ['relevant', 'core', 'supply', 'all'];
/** Value presets, plain numbers: they apply in the selected currency. Nothing is converted. */
const VALUE_PRESETS = [100_000, 500_000, 1_000_000, 5_000_000, 10_000_000, 50_000_000];
const formatPreset = (n: number) => (n >= 1_000_000 ? `${n / 1_000_000}M` : `${n / 1_000}k`);

const FORM = 'flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5';

function CountryChoices({ selected }: { selected: string[] | undefined }) {
  return (
    <FoldGroup legend="Buyer country" open={false} scroll count={selected?.length}>
      {Object.keys(BUYER_COUNTRIES).map((c) => (
        <Choice key={c} name={PARAM.country} value={c} defaultChecked={selected?.includes(c)}
          label={<span className="inline-flex gap-2"><span className="font-mono text-mono-strong">{c}</span><span className="sr-only">{'\u00a0'}</span>{BUYER_COUNTRIES[c]}</span>} />
      ))}
    </FoldGroup>
  );
}

/**
 * URL-synced filter form (GET) for /tenders. Works without JS; FilterPanel enhances it. The same
 * progressive-enhancement panel as the funding filters.
 */
export function TenderFilterBar({ filters, basePath, scopeCounts, countsNote }: {
  filters: TenderFilters; basePath: string; scopeCounts?: ScopeCounts | null;
  /** WP-87 (lib/list-count.ts listStamps): the scope counts' own time, when it is not the list's; null when the header says it. */
  countsNote?: string | null;
}) {
  const currency = filters.currency ?? DEFAULT_CURRENCY;
  const currencyOptions = (CURRENCIES.includes(currency) ? [...CURRENCIES] : [...CURRENCIES, currency]).map((c) => ({ value: c, label: c }));
  const valueOptions = VALUE_PRESETS.map((n) => ({ value: String(n), label: `${currency} ${formatPreset(n)}` }));
  // A value typed into the URL that is not a preset stays selectable, so the form never silently drops it.
  const withCurrent = (v: number | undefined) => (v === undefined || VALUE_PRESETS.includes(v) ? valueOptions : [...valueOptions, { value: String(v), label: `${currency} ${v}` }]);
  const asOf = countsNote === undefined ? countsAsOf(scopeCounts?.asOf) : countsNote;
  const overlap = overlapNote(scopeCounts);
  return (
    <FilterPanel activeCount={activeTenderFilterCount(filters)} defaults={{ [PARAM.status]: DEFAULT_TENDER_STATUS, [PARAM.scope]: DEFAULT_TENDER_SCOPE }}>
      <form method="get" action={basePath} role="search" aria-label="Filter tenders" className={FORM}>
        <TextInput search name={PARAM.q} maxLength={MAX_QUERY_LENGTH} label="Search" placeholder="Title, buyer or number" defaultValue={filters.q ?? ''} />
        <TextInput name={PARAM.cpv} maxLength={200} label="CPV code" placeholder="For example 35 or 35120000" defaultValue={filters.cpv?.join(', ') ?? ''}
          hint="Starts with the digits you enter. Separate several with commas." />
        <FoldGroup legend="Status">
          {STATUS_OPTIONS.map((o) => <Choice key={o.value} type="radio" name={PARAM.status} value={o.value} label={o.label} defaultChecked={(filters.status ?? DEFAULT_TENDER_STATUS) === o.value} />)}
        </FoldGroup>
        <FoldGroup legend="Scope" count={filters.goods === 'defence' ? 1 : 0}>
          {SCOPE_OPTIONS.map((o) => {
            const n = o === 'all' ? undefined : scopeCounts?.[o];
            return (
              <Choice key={o} type="radio" name={PARAM.scope} value={o}
                label={<span>{SCOPE_CHOICES[o].label}{n !== undefined && <span className="font-mono text-mono-strong tabular-nums">{scopeCountText(n, scopeCounts?.capped)}</span>}</span>}
                defaultChecked={(filters.scope ?? DEFAULT_TENDER_SCOPE) === o} />
            );
          })}
          <p className="m-0 pt-1 text-small text-ink-muted">
            {asOf ? `${asOf}, for the other filters as they are now.` : 'Counts are for the other filters as they are now.'} {overlap && <>{overlap} </>}<Link href="/glossary#scope" className="font-semibold">What the scopes mean</Link>
          </p>
          <Choice name={PARAM.goods} value="defence" label="Defence goods only" defaultChecked={filters.goods === 'defence'}
            hint="Narrows the scope you chose to notices that say defence themselves: the directive or a military product code." />
        </FoldGroup>
        <CountryChoices selected={filters.country} />
        <FoldGroup legend="Deadline between (UTC)" open={false} count={(filters.deadlineFrom ? 1 : 0) + (filters.deadlineTo ? 1 : 0)}>
          <TextInput type="date" name={PARAM.from} aria-label="Deadline from" defaultValue={filters.deadlineFrom ?? ''} />
          <TextInput type="date" name={PARAM.to} aria-label="Deadline to" defaultValue={filters.deadlineTo ?? ''} />
        </FoldGroup>
        <FoldGroup legend="Estimated value" open={false} count={(filters.currency ? 1 : 0) + (filters.valueMin ? 1 : 0) + (filters.valueMax ? 1 : 0)}>
          <Select name={PARAM.currency} aria-label="Value currency" placeholder="Any currency" options={currencyOptions} defaultValue={filters.currency ?? ''} />
          <Select name={PARAM.min} aria-label="Minimum value" placeholder="No minimum" options={withCurrent(filters.valueMin)} defaultValue={filters.valueMin?.toString() ?? ''} />
          <Select name={PARAM.max} aria-label="Maximum value" placeholder="No maximum" options={withCurrent(filters.valueMax)} defaultValue={filters.valueMax?.toString() ?? ''} />
          <p className="m-0 text-small text-ink-muted">
            A currency alone lists the notices that state a value in it. A minimum or maximum is read in that currency (EUR when none is chosen) and
            leaves out notices with no stated value. Nothing is converted.
          </p>
        </FoldGroup>
        {/* Only a sort that was asked for travels with the form: the default follows the status (a closed list runs newest first). */}
        {filters.sort && filters.sort !== defaultTenderSort(filters.status) && <input type="hidden" name={PARAM.sort} value={filters.sort} />}
        <div className={FORM_BUTTONS}>
          <Button type="submit">Apply filters</Button>
          <Link href={basePath} className="inline-flex min-h-11 items-center text-small font-bold">Clear all</Link>
        </div>
      </form>
    </FilterPanel>
  );
}

/** URL-synced filter form (GET) for /buyers. */
export function BuyerFilterBar({ filters, basePath }: { filters: BuyerFilters; basePath: string }) {
  return (
    <FilterPanel activeCount={activeBuyerFilterCount(filters)}>
      <form method="get" action={basePath} role="search" aria-label="Filter buyers" className={FORM}>
        <TextInput search name={PARAM.q} maxLength={MAX_QUERY_LENGTH} label="Search" placeholder="Name of the buyer" defaultValue={filters.q ?? ''} />
        <FoldGroup legend="Open tenders" count={filters.hasOpen === true ? 1 : 0}>
          <Choice name={PARAM.hasOpen} value="true" label="Only buyers with open tenders" defaultChecked={filters.hasOpen === true} />
        </FoldGroup>
        <CountryChoices selected={filters.country} />
        {filters.sort && <input type="hidden" name={PARAM.sort} value={filters.sort} />}
        <div className={FORM_BUTTONS}>
          <Button type="submit">Apply filters</Button>
          <Link href={basePath} className="inline-flex min-h-11 items-center text-small font-bold">Clear all</Link>
        </div>
      </form>
    </FilterPanel>
  );
}
