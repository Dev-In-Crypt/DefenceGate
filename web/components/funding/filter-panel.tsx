'use client';

import { useEffect, useRef, useState, useTransition } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { SlidersHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from '../dg/icon';
import { boxCls } from '../dg/field';
import { ListboxSelect } from '../dg/select';

/** Turns form data into a clean query string (drops empty values and the default currency, joins repeats with commas). */
function formToQuery(form: HTMLFormElement): string {
  const fd = new FormData(form);
  const map = new Map<string, string[]>();
  for (const [k, v] of fd.entries()) {
    if (typeof v !== 'string' || v === '') continue;
    if (k === 'currency' && v === 'EUR') continue; // the default stays out of the URL
    map.set(k, [...(map.get(k) ?? []), v]);
  }
  const p = new URLSearchParams();
  for (const [k, vals] of map) p.set(k, vals.join(','));
  p.delete('page');
  const s = p.toString();
  return s ? `?${s}` : '';
}

/**
 * Progressive enhancement for the GET filter form: without JS the form submits normally;
 * with JS, checkbox/select/date changes update the URL immediately (shareable, no reload).
 * Below lg the panel collapses behind a "Show filters" button; from lg the column holding it is sticky (the page's list shell).
 */
export function FilterPanel({ activeCount, children }: { activeCount: number; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    const form = ref.current?.querySelector('form');
    if (!form) return;
    const push = () => startTransition(() => router.replace(`${pathname}${formToQuery(form)}`, { scroll: false }));
    const onChange = (e: Event) => { if ((e.target as HTMLInputElement).type !== 'search') push(); };
    const onSubmit = (e: SubmitEvent) => { e.preventDefault(); push(); };
    form.addEventListener('change', onChange);
    form.addEventListener('submit', onSubmit);
    return () => { form.removeEventListener('change', onChange); form.removeEventListener('submit', onSubmit); };
  }, [pathname, router]);

  return (
    <div ref={ref} aria-busy={pending} className="flex flex-col gap-3">
      <button type="button" aria-expanded={open} aria-controls="filter-panel" onClick={() => setOpen(!open)}
        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-pill border-strong border-ink bg-surface px-5 text-small font-bold text-ink lg:hidden">
        <Icon icon={SlidersHorizontal} size="button" />
        {open ? 'Hide filters' : 'Show filters'}{activeCount > 0 ? ` · ${activeCount} active` : ''}
      </button>
      <div id="filter-panel" className={cn(open ? 'block' : 'hidden', 'lg:block')}>{children}</div>
    </div>
  );
}

/** Sort select outside the filter form; preserves all other params. */
export function SortSelect({ value, options }: { value: string; options: { value: string; label: string }[] }) {
  const router = useRouter();
  const pathname = usePathname();
  return (
    <label className="flex items-center gap-2 text-small font-semibold">
      <span>Sort</span>
      <span className={cn(boxCls(undefined, false, true), 'relative')}>
        <ListboxSelect value={value} options={options} accessibleName="Sort"
          className="text-small font-semibold" onChange={(e) => {
            const p = new URLSearchParams(window.location.search);
            p.set('sort', e.target.value); p.delete('page');
            router.replace(`${pathname}?${p}`, { scroll: false });
          }} />
      </span>
    </label>
  );
}
