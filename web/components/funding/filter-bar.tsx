import Link from 'next/link';
import { Button } from '../dg/button';
import { Choice, FoldGroup, Select, TextInput } from '../dg/form';
import { FilterPanel } from './filter-panel';
import { COUNTRIES, CURRENCIES, FUNDER_COUNTRIES, PROGRAMMES, PROGRAMME_CODES, REGIMES, REGIME_CODES } from '@/lib/taxonomy';
import { DEFAULT_CURRENCY, DEFAULT_STATUS, MAX_QUERY_LENGTH, PARAM, activeFilterCount, defaultCallSort } from '@/lib/filters';
import type { CallFilters, CallStatusFilter, CountryCode } from '@/lib/types';

export type FilterGroup = 'status' | 'programme' | 'regime' | 'country' | 'cascade' | 'ukraine';

const STATUS_OPTIONS: { value: CallStatusFilter; label: string }[] = [
  { value: 'open', label: 'Open' }, { value: 'forthcoming', label: 'Opens soon' },
  { value: 'closing-soon', label: 'Closing soon (30 days)' },
  { value: 'closed', label: 'Closed' }, { value: 'all', label: 'All' },
];
/** Budget presets, as plain numbers: they apply in the selected currency. Nothing is converted. */
/** A filter form: groups that fold, separated by hairlines; the buttons stay at the foot of the visible part. */
const FORM = 'flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5';
export const FORM_BUTTONS = 'sticky bottom-0 z-10 -mx-5 -mb-5 flex flex-wrap items-center gap-3 rounded-b-lg border-t border-line bg-surface px-5 py-3';
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
    <FilterPanel activeCount={activeFilterCount(filters)} defaults={{ [PARAM.status]: DEFAULT_STATUS }}>
      <form method="get" action={basePath} role="search" aria-label="Filter funding calls" className={FORM}>
        <TextInput search name={PARAM.q} maxLength={MAX_QUERY_LENGTH} label="Search" placeholder="Title, call ID or keyword" defaultValue={filters.q ?? ''} hint="Whole words; counter-drone and counter drone are the same, and drone also finds unmanned." />
        {show('status') && (
          <FoldGroup legend="Status">
            {STATUS_OPTIONS.map((o) => <Choice key={o.value} type="radio" name={PARAM.status} value={o.value} label={o.label} defaultChecked={(filters.status ?? 'open') === o.value} />)}
          </FoldGroup>
        )}
        {show('programme') && (
          <FoldGroup legend="Programme" count={filters.programme?.length}>
            {/* EDIP calls are filed under EDF by the portal: an EDIP filter would always be empty. */}
            {PROGRAMME_CODES.filter((p) => p !== 'EDIP').map((p) => <Choice key={p} name={PARAM.programme} value={p} label={p === 'EDF' ? 'EDF (with EDIP)' : PROGRAMMES[p].label} defaultChecked={filters.programme?.includes(p)} />)}
          </FoldGroup>
        )}
        {show('regime') && (
          <FoldGroup legend="Defence or dual-use" count={filters.regime?.length}>
            {REGIME_CODES.map((r) => <Choice key={r} name={PARAM.regime} value={r} label={REGIMES[r]} defaultChecked={filters.regime?.includes(r)} />)}
            <p className="m-0 text-small text-ink-muted">
              Dual-use is our label for calls under civil programmes we treat as dual-use. It is not the programme’s label.
              See the <Link href="/methodology#s-what-defence-and-dual-use-mean-here" className="font-semibold">rule</Link> and the <Link href="/glossary#dual-use" className="font-semibold">glossary</Link>.
            </p>
          </FoldGroup>
        )}
        {show('country') && (
          <FoldGroup legend="Funder country" open={false} scroll count={filters.country?.length}>
            {countries.map((c) => (
              <Choice key={c} name={PARAM.country} value={c} defaultChecked={filters.country?.includes(c)}
                label={<span className="inline-flex gap-2"><span className="font-mono text-mono-strong">{c}</span><span className="sr-only">{'\u00a0'}</span>{COUNTRIES[c]}</span>} />
            ))}
          </FoldGroup>
        )}
        {show('cascade') && (
          <FoldGroup legend="Cascade funding" count={filters.cascade === true ? 1 : 0}>
            <Choice name={PARAM.cascade} value="true" defaultChecked={filters.cascade === true}
              label={`Only calls with cascade funding${typeof cascadeTotal === 'number' ? ` (${cascadeTotal})` : ''}`} />
            <p className="m-0 text-small text-ink-muted">
              The call passes part of its money to third parties, usually small firms, by calls of its own.
              A call is counted only where its text or document says so; see the <Link href="/glossary#cascade-funding" className="font-semibold">glossary</Link>.
            </p>
          </FoldGroup>
        )}
        {show('ukraine') && (
          <FoldGroup legend="Ukrainian participants" count={filters.ukraine === true ? 1 : 0}>
            <Choice name={PARAM.ukraine} value="true" defaultChecked={filters.ukraine === true}
              label={`Only calls open to Ukraine${typeof ukraineTotal === 'number' ? ` (${ukraineTotal})` : ''}`} />
            <p className="m-0 text-small text-ink-muted">
              A call is counted only where its document, its text or its programme’s regulation says Ukrainian entities may take part.
              A call that is not counted may still be open: its answer is unknown. See the <Link href="/glossary#open-to-ukraine" className="font-semibold">glossary</Link>.
            </p>
          </FoldGroup>
        )}
        <FoldGroup legend="Deadline between (UTC)" open={false} count={(filters.deadlineFrom ? 1 : 0) + (filters.deadlineTo ? 1 : 0)}>
          <TextInput type="date" name={PARAM.from} aria-label="Deadline from" defaultValue={filters.deadlineFrom ?? ''} />
          <TextInput type="date" name={PARAM.to} aria-label="Deadline to" defaultValue={filters.deadlineTo ?? ''} />
        </FoldGroup>
        <FoldGroup legend="Budget" open={false} count={(filters.currency ? 1 : 0) + (filters.budgetMin ? 1 : 0) + (filters.budgetMax ? 1 : 0)}>
          <Select name={PARAM.currency} aria-label="Budget currency" placeholder="Any currency" options={currencyOptions} defaultValue={filters.currency ?? ''} />
          <Select name={PARAM.min} aria-label="Minimum budget" placeholder="No minimum" options={budgetOptions} defaultValue={filters.budgetMin?.toString() ?? ''} />
          <Select name={PARAM.max} aria-label="Maximum budget" placeholder="No maximum" options={budgetOptions} defaultValue={filters.budgetMax?.toString() ?? ''} />
          <p className="m-0 text-small text-ink-muted">
            A currency alone lists the calls that state a budget in it. A minimum or maximum is read in that currency (EUR when none is chosen) and
            leaves out calls with no stated budget. Nothing is converted.
          </p>
        </FoldGroup>
        {/* Only a sort the visitor chose travels on: the default depends on the status, which the form may change. */}
        {filters.sort && filters.sort !== defaultCallSort(filters.status) && <input type="hidden" name={PARAM.sort} value={filters.sort} />}
        {view && <input type="hidden" name={PARAM.view} value={view} />}
        <div className={FORM_BUTTONS}>
          <Button type="submit">Apply filters</Button>
          <Link href={basePath} className="inline-flex min-h-11 items-center text-small font-bold">Clear all</Link>
        </div>
      </form>
    </FilterPanel>
  );
}
