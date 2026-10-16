import Link from 'next/link';
import { Button } from '../dg/button';
import { Choice, Fieldset, Select, TextInput } from '../dg/form';
import { FilterPanel } from '../funding/filter-panel';
import { BUYER_COUNTRIES, CURRENCIES, SCOPE_CHOICES } from '@/lib/taxonomy';
import {
  DEFAULT_CURRENCY, DEFAULT_TENDER_SCOPE, DEFAULT_TENDER_STATUS, MAX_QUERY_LENGTH, PARAM, activeBuyerFilterCount, activeTenderFilterCount,
  defaultTenderSort,
} from '@/lib/filters';
import { formatNumber } from '@/lib/format';
import type { BuyerFilters, ScopeCounts, TenderFilters, TenderScopeFilter, TenderStatusFilter } from '@/lib/types';

const STATUS_OPTIONS: { value: TenderStatusFilter; label: string }[] = [
  { value: 'open', label: 'Open' }, { value: 'closed', label: 'Closed' }, { value: 'all', label: 'All' },
];
/** The scope choices, in the order of the glossary (lib/taxonomy.ts SCOPE_CHOICES); `all` is the escape hatch. */
const SCOPE_OPTIONS: TenderScopeFilter[] = ['relevant', 'core', 'supply', 'all'];
/** Value presets, plain numbers: they apply in the selected currency. Nothing is converted. */
const VALUE_PRESETS = [100_000, 500_000, 1_000_000, 5_000_000, 10_000_000, 50_000_000];
const formatPreset = (n: number) => (n >= 1_000_000 ? `${n / 1_000_000}M` : `${n / 1_000}k`);

const FORM = 'flex flex-col gap-6 rounded-lg bg-surface p-5';

function CountryChoices({ selected }: { selected: string[] | undefined }) {
  return (
    <Fieldset legend="Buyer country">
      {Object.keys(BUYER_COUNTRIES).map((c) => (
        <Choice key={c} name={PARAM.country} value={c} defaultChecked={selected?.includes(c)}
          label={<span className="inline-flex gap-2"><span className="font-mono text-mono-strong">{c}</span>{BUYER_COUNTRIES[c]}</span>} />
      ))}
    </Fieldset>
  );
}

/**
 * URL-synced filter form (GET) for /tenders. Works without JS; FilterPanel enhances it. The same
 * progressive-enhancement panel as the funding filters.
 */
export function TenderFilterBar({ filters, basePath, scopeCounts }: { filters: TenderFilters; basePath: string; scopeCounts?: ScopeCounts | null }) {
  const currency = filters.currency ?? DEFAULT_CURRENCY;
  const currencyOptions = (CURRENCIES.includes(currency) ? [...CURRENCIES] : [...CURRENCIES, currency]).map((c) => ({ value: c, label: c }));
  const valueOptions = VALUE_PRESETS.map((n) => ({ value: String(n), label: `${currency} ${formatPreset(n)}` }));
  // A value typed into the URL that is not a preset stays selectable, so the form never silently drops it.
  const withCurrent = (v: number | undefined) => (v === undefined || VALUE_PRESETS.includes(v) ? valueOptions : [...valueOptions, { value: String(v), label: `${currency} ${v}` }]);
  return (
    <FilterPanel activeCount={activeTenderFilterCount(filters)}>
      <form method="get" action={basePath} role="search" aria-label="Filter tenders" className={FORM}>
        <TextInput search name={PARAM.q} maxLength={MAX_QUERY_LENGTH} label="Search" placeholder="Title, buyer or notice number" defaultValue={filters.q ?? ''} />
        <TextInput name={PARAM.cpv} maxLength={200} label="CPV code" placeholder="For example 35 or 35120000" defaultValue={filters.cpv?.join(', ') ?? ''}
          hint="Starts with the digits you enter. Separate several with commas." />
        <Fieldset legend="Status">
          {STATUS_OPTIONS.map((o) => <Choice key={o.value} type="radio" name={PARAM.status} value={o.value} label={o.label} defaultChecked={(filters.status ?? DEFAULT_TENDER_STATUS) === o.value} />)}
        </Fieldset>
        <Fieldset legend="Scope">
          {SCOPE_OPTIONS.map((o) => {
            const n = o === 'all' ? undefined : scopeCounts?.[o];
            return (
              <Choice key={o} type="radio" name={PARAM.scope} value={o}
                label={<span>{SCOPE_CHOICES[o].label}{n !== undefined && <span className="font-mono text-mono-strong tabular-nums"> ({formatNumber(n)})</span>}</span>}
                defaultChecked={(filters.scope ?? DEFAULT_TENDER_SCOPE) === o} />
            );
          })}
          <p className="m-0 pt-1 text-small text-ink-muted">
            Counts are for the other filters as they are now. <Link href="/glossary#scope" className="font-semibold">What the scopes mean</Link>
          </p>
          <Choice name={PARAM.goods} value="defence" label="Defence goods only" defaultChecked={filters.goods === 'defence'}
            hint="Narrows the scope you chose to notices that say defence themselves: the directive or a military product code." />
        </Fieldset>
        <CountryChoices selected={filters.country} />
        <Fieldset legend="Deadline between (UTC)" className="gap-2">
          <TextInput type="date" name={PARAM.from} aria-label="Deadline from" defaultValue={filters.deadlineFrom ?? ''} />
          <TextInput type="date" name={PARAM.to} aria-label="Deadline to" defaultValue={filters.deadlineTo ?? ''} />
        </Fieldset>
        <Fieldset legend="Estimated value" className="gap-2">
          <Select name={PARAM.currency} aria-label="Value currency" options={currencyOptions} defaultValue={currency} />
          <Select name={PARAM.min} aria-label="Minimum value" placeholder="No minimum" options={withCurrent(filters.valueMin)} defaultValue={filters.valueMin?.toString() ?? ''} />
          <Select name={PARAM.max} aria-label="Maximum value" placeholder="No maximum" options={withCurrent(filters.valueMax)} defaultValue={filters.valueMax?.toString() ?? ''} />
          <p className="m-0 text-small text-ink-muted">A value range selects notices stated in that one currency. Nothing is converted.</p>
        </Fieldset>
        {/* Only a sort that was asked for travels with the form: the default follows the status (a closed list runs newest first). */}
        {filters.sort && filters.sort !== defaultTenderSort(filters.status) && <input type="hidden" name={PARAM.sort} value={filters.sort} />}
        <div className="flex flex-wrap items-center gap-3">
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
        <Fieldset legend="Open tenders">
          <Choice name={PARAM.hasOpen} value="true" label="Only buyers with open tenders" defaultChecked={filters.hasOpen === true} />
        </Fieldset>
        <CountryChoices selected={filters.country} />
        {filters.sort && <input type="hidden" name={PARAM.sort} value={filters.sort} />}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit">Apply filters</Button>
          <Link href={basePath} className="inline-flex min-h-11 items-center text-small font-bold">Clear all</Link>
        </div>
      </form>
    </FilterPanel>
  );
}
