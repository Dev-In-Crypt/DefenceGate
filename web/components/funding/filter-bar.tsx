import Link from 'next/link';
import { Button } from '../dg/button';
import { Choice, Fieldset, Select, TextInput } from '../dg/form';
import { FilterPanel } from './filter-panel';
import { COUNTRIES, CURRENCIES, FUNDER_COUNTRIES, PROGRAMMES, PROGRAMME_CODES, REGIMES, REGIME_CODES } from '@/lib/taxonomy';
import { DEFAULT_CURRENCY, MAX_QUERY_LENGTH, PARAM, activeFilterCount, defaultCallSort } from '@/lib/filters';
import type { CallFilters, CallStatusFilter, CountryCode } from '@/lib/types';

export type FilterGroup = 'status' | 'programme' | 'regime' | 'country' | 'cascade' | 'ukraine';

const STATUS_OPTIONS: { value: CallStatusFilter; label: string }[] = [
  { value: 'open', label: 'Open' }, { value: 'forthcoming', label: 'Opens soon' },
  { value: 'closing-soon', label: 'Closing soon (30 days)' },
  { value: 'closed', label: 'Closed' }, { value: 'all', label: 'All' },
];
/** Budget presets, as plain numbers: they apply in the selected currency. Nothing is converted. */
const BUDGET_PRESETS = [1_000_000, 5_000_000, 10_000_000, 25_000_000, 50_000_000];

/**
 * URL-synced filter form (GET). Works without JS; FilterPanel enhances it.
 * `hide` removes groups fixed by a sub-page (e.g. a sub-page fixed to one country hides country).
 * `countries` is the list of funder countries with coverage (see fundersWithCoverage); default is all.
 */
export function FilterBar({ filters, basePath, hide = [], view, countries = FUNDER_COUNTRIES, cascadeTotal, ukraineTotal }: {
  filters: CallFilters; basePath: string; hide?: FilterGroup[]; view?: string; countries?: CountryCode[];
  /** Calls with cascade funding among those that match the other filters (the API's `cascadeTotal`); absent: no count. */
  cascadeTotal?: number | null;
  /** Calls open to Ukrainian participants among those that match the other filters (the API's `ukraineTotal`); absent: no count. */
  ukraineTotal?: number | null;
}) {
  const show = (g: FilterGroup) => !hide.includes(g);
  const currency = filters.currency ?? DEFAULT_CURRENCY;
  // EUR first, then the other currencies we collect; a currency from the URL stays selectable.
  const currencyOptions = (CURRENCIES.includes(currency) ? [...CURRENCIES] : [...CURRENCIES, currency]).map((c) => ({ value: c, label: c }));
  const budgetOptions = BUDGET_PRESETS.map((n) => ({ value: String(n), label: `${currency} ${n / 1_000_000}M` }));
  return (
    <FilterPanel activeCount={activeFilterCount(filters)}>
      <form method="get" action={basePath} role="search" aria-label="Filter funding calls" className="flex flex-col gap-6 rounded-lg border border-edge bg-surface p-5">
        <TextInput search name={PARAM.q} maxLength={MAX_QUERY_LENGTH} label="Search" placeholder="Title, call ID or keyword" defaultValue={filters.q ?? ''} hint="Whole words; counter-drone and counter drone are the same, and drone also finds unmanned." />
        {show('status') && (
          <Fieldset legend="Status">
            {STATUS_OPTIONS.map((o) => <Choice key={o.value} type="radio" name={PARAM.status} value={o.value} label={o.label} defaultChecked={(filters.status ?? 'open') === o.value} />)}
          </Fieldset>
        )}
        {show('programme') && (
          <Fieldset legend="Programme">
            {/* EDIP calls are filed under EDF by the portal: an EDIP filter would always be empty. */}
            {PROGRAMME_CODES.filter((p) => p !== 'EDIP').map((p) => <Choice key={p} name={PARAM.programme} value={p} label={p === 'EDF' ? 'EDF (with EDIP)' : PROGRAMMES[p].label} defaultChecked={filters.programme?.includes(p)} />)}
          </Fieldset>
        )}
        {show('regime') && (
          <Fieldset legend="Regime">
            {REGIME_CODES.map((r) => <Choice key={r} name={PARAM.regime} value={r} label={REGIMES[r]} defaultChecked={filters.regime?.includes(r)} />)}
            <p className="m-0 text-small text-ink-muted">
              Dual-use is our label for calls under civil programmes we treat as dual-use. It is not the programme’s label.
              See the <Link href="/methodology#s-what-defence-and-dual-use-mean-here" className="font-semibold">rule</Link> and the <Link href="/glossary#dual-use" className="font-semibold">glossary</Link>.
            </p>
          </Fieldset>
        )}
        {show('country') && (
          <Fieldset legend="Funder country">
            {countries.map((c) => (
              <Choice key={c} name={PARAM.country} value={c} defaultChecked={filters.country?.includes(c)}
                label={<span className="inline-flex gap-2"><span className="font-mono text-mono-strong">{c}</span>{COUNTRIES[c]}</span>} />
            ))}
          </Fieldset>
        )}
        {show('cascade') && (
          <Fieldset legend="Financial support to third parties">
            <Choice name={PARAM.cascade} value="true" defaultChecked={filters.cascade === true}
              label={`Only calls with cascade funding${typeof cascadeTotal === 'number' ? ` (${cascadeTotal})` : ''}`} />
            <p className="m-0 text-small text-ink-muted">
              The call passes part of its money to third parties, usually small firms, by calls of its own.
              A call is counted only where its text or document says so; see the <Link href="/glossary#cascade-funding" className="font-semibold">glossary</Link>.
            </p>
          </Fieldset>
        )}
        {show('ukraine') && (
          <Fieldset legend="Ukrainian participants">
            <Choice name={PARAM.ukraine} value="true" defaultChecked={filters.ukraine === true}
              label={`Only calls open to Ukraine${typeof ukraineTotal === 'number' ? ` (${ukraineTotal})` : ''}`} />
            <p className="m-0 text-small text-ink-muted">
              A call is counted only where its document, its text or its programme’s regulation says Ukrainian entities may take part.
              A call that is not counted may still be open: its answer is unknown. See the <Link href="/glossary#open-to-ukraine" className="font-semibold">glossary</Link>.
            </p>
          </Fieldset>
        )}
        <Fieldset legend="Deadline between (UTC)" className="gap-2">
          <TextInput type="date" name={PARAM.from} aria-label="Deadline from" defaultValue={filters.deadlineFrom ?? ''} />
          <TextInput type="date" name={PARAM.to} aria-label="Deadline to" defaultValue={filters.deadlineTo ?? ''} />
        </Fieldset>
        <Fieldset legend="Budget" className="gap-2">
          <Select name={PARAM.currency} aria-label="Budget currency" options={currencyOptions} defaultValue={currency} />
          <Select name={PARAM.min} aria-label="Minimum budget" placeholder="No minimum" options={budgetOptions} defaultValue={filters.budgetMin?.toString() ?? ''} />
          <Select name={PARAM.max} aria-label="Maximum budget" placeholder="No maximum" options={budgetOptions} defaultValue={filters.budgetMax?.toString() ?? ''} />
          <p className="m-0 text-small text-ink-muted">Amounts are shown and filtered in the currency the source states. Nothing is converted.</p>
        </Fieldset>
        {/* Only a sort the visitor chose travels on: the default depends on the status, which the form may change. */}
        {filters.sort && filters.sort !== defaultCallSort(filters.status) && <input type="hidden" name={PARAM.sort} value={filters.sort} />}
        {view && <input type="hidden" name={PARAM.view} value={view} />}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit">Apply filters</Button>
          <Link href={basePath} className="inline-flex min-h-11 items-center text-small font-bold">Clear all</Link>
        </div>
      </form>
    </FilterPanel>
  );
}
