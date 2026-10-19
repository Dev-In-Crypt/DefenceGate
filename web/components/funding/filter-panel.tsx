'use client';

import { useEffect, useRef, useState, useTransition } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { LoaderCircle, SlidersHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from '../dg/icon';
import { boxCls } from '../dg/field';
import { ListboxSelect } from '../dg/select';
import { useReportBusy } from '../dg/live-list';
import { canonQuery, queryFromEntries, type FormDefaults } from '@/lib/filter-query';

/** A tick on a checkbox waits this long for the next one before the list is asked for: three ticks make one request. */
export const CHECKBOX_DEBOUNCE_MS = 400;

/** Turns the form's data into a clean query string (see `queryFromEntries`). */
function formToQuery(form: HTMLFormElement, defaults: FormDefaults = {}): string {
  return queryFromEntries(new FormData(form).entries(), defaults);
}

/**
 * Makes the first `<form>` inside `ref` live (progressive enhancement: without scripts it is a plain GET form with its button).
 *
 *  - A checkbox waits `CHECKBOX_DEBOUNCE_MS` for the next tick; a radio, a select, a date and the submit (Enter, the button)
 *    apply at once. A search box applies on Enter only, a text box when it is left.
 *  - One history entry per settled filter set (`router.push`), so Back undoes the last change. A set equal to the one in the
 *    address (or already on its way) is not sent.
 *  - `pending` is true from the request until the new list is there.
 *  - When the address changes from outside the form (Back, Forward, a "Clear all" link) the form is rebuilt from the new page,
 *    unless the visitor is in the middle of a change. `epoch` is the key that does it.
 */
function useLiveForm(ref: React.RefObject<HTMLElement | null>, defaults: FormDefaults, children: React.ReactNode) {
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();
  const [epoch, setEpoch] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sent = useRef<string | null>(null);
  const busy = useRef(false);
  const first = useRef(true);
  const defaultsKey = JSON.stringify(defaults);

  busy.current = pending;
  useEffect(() => { if (!pending) sent.current = null; }, [pending]);
  useReportBusy(pending);

  useEffect(() => {
    const form = ref.current?.querySelector('form');
    if (!form) return;
    const d: FormDefaults = JSON.parse(defaultsKey);
    const go = () => {
      if (timer.current) { clearTimeout(timer.current); timer.current = null; }
      const query = formToQuery(form, d);
      if (canonQuery(query, d) === canonQuery(sent.current ?? window.location.search, d)) return;
      sent.current = query;
      startTransition(() => router.push(`${pathname}${query}`, { scroll: false }));
    };
    const onChange = (e: Event) => {
      const t = e.target as HTMLInputElement;
      if (t.type === 'search') return;
      if (t.type !== 'checkbox') return go();
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(go, CHECKBOX_DEBOUNCE_MS);
    };
    const onSubmit = (e: SubmitEvent) => { e.preventDefault(); go(); };
    form.addEventListener('change', onChange);
    form.addEventListener('submit', onSubmit);
    return () => {
      form.removeEventListener('change', onChange);
      form.removeEventListener('submit', onSubmit);
      if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    };
  }, [pathname, router, ref, defaultsKey, epoch]);

  // A new page of this route arrived (new children). If the address now differs from the form, someone else moved it.
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    // Whatever was sent has landed (a navigation that finished at once never shows `pending`, so this is the reset that matters).
    if (!busy.current) sent.current = null;
    const form = ref.current?.querySelector('form');
    if (!form || timer.current || busy.current) return;
    const d: FormDefaults = JSON.parse(defaultsKey);
    if (canonQuery(formToQuery(form, d), d) !== canonQuery(window.location.search, d)) setEpoch((e) => e + 1);
  }, [children, ref, defaultsKey]);

  return { pending, epoch };
}

/**
 * The GET filter form made live: checkbox/select/date changes update the address (shareable, no reload), see `useLiveForm`.
 * Below lg the panel collapses behind a "Show filters" button; from lg the column holding it is sticky (the page's list shell).
 * `defaults` are the values the page assumes when they are not in the address (status=open...): they stay out of it.
 */
export function FilterPanel({ activeCount, defaults = {}, children }: { activeCount: number; defaults?: FormDefaults; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const { pending, epoch } = useLiveForm(ref, defaults, children);

  return (
    <div ref={ref} aria-busy={pending} className="flex flex-col gap-3">
      <button type="button" aria-expanded={open} aria-controls="filter-panel" onClick={() => setOpen(!open)}
        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-pill border-strong border-ink bg-surface px-5 text-small font-bold text-ink lg:hidden">
        <Icon icon={pending ? LoaderCircle : SlidersHorizontal} size="button" className={cn(pending && 'motion-safe:animate-spin')} />
        {open ? 'Hide filters' : 'Show filters'}{activeCount > 0 ? ` · ${activeCount} active` : ''}{pending ? ' · updating' : ''}
      </button>
      <span role="status" className="sr-only">{pending ? 'Updating the results' : ''}</span>
      <div key={epoch} id="filter-panel" className={cn(open ? 'block' : 'hidden', 'lg:block')}>{children}</div>
    </div>
  );
}

/** A live filter form that is not a collapsible column (the horizontal form of /suppliers). Same behaviour as `FilterPanel`. */
export function LiveForm({ defaults = {}, children }: { defaults?: FormDefaults; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const { pending, epoch } = useLiveForm(ref, defaults, children);
  return (
    <div ref={ref} aria-busy={pending}>
      <span role="status" className="sr-only">{pending ? 'Updating the results' : ''}</span>
      <div key={epoch}>{children}</div>
    </div>
  );
}

/** Sort select outside the filter form; preserves all other params. One history entry per choice. */
export function SortSelect({ value, options }: { value: string; options: { value: string; label: string }[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();
  useReportBusy(pending);
  return (
    <label className="flex items-center gap-2 text-small font-semibold">
      <span>Sort</span>
      <span className={cn(boxCls(undefined, false, true), 'relative')}>
        <ListboxSelect value={value} options={options} accessibleName="Sort"
          className="text-small font-semibold" onChange={(e) => {
            const p = new URLSearchParams(window.location.search);
            p.set('sort', e.target.value); p.delete('page');
            startTransition(() => router.push(`${pathname}?${p}`, { scroll: false }));
          }} />
      </span>
    </label>
  );
}
