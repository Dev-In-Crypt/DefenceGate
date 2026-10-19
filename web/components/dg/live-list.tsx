'use client';

import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useLinkStatus } from 'next/link';
import { cn } from '@/lib/utils';

/**
 * The "the list is loading" state of a results page. Whatever asks for a new list (the filter form, the sort select, a
 * pagination link) reports itself here with `useReportBusy`; the results region (`ResultsRegion`) then dims and shows a bar,
 * and carries `aria-busy`. The previous list stays on screen and clickable meanwhile (WP-49: a filter change used to give
 * no sign for the 1 to 5 s a new combination takes on a cold query).
 */
type Busy = { inc: () => void; dec: () => void };
const BusyApi = createContext<Busy | null>(null);
const BusyNow = createContext(false);

export function LiveListScope({ children }: { children: React.ReactNode }) {
  const [n, setN] = useState(0);
  const api = useMemo<Busy>(() => ({ inc: () => setN((v) => v + 1), dec: () => setN((v) => Math.max(0, v - 1)) }), []);
  return (
    <BusyApi.Provider value={api}>
      <BusyNow.Provider value={n > 0}>{children}</BusyNow.Provider>
    </BusyApi.Provider>
  );
}

/** Report that something is loading a new list while `pending` is true. Outside a `LiveListScope` it does nothing. */
export function useReportBusy(pending: boolean) {
  const api = useContext(BusyApi);
  useEffect(() => {
    if (!pending || !api) return;
    api.inc();
    return () => api.dec();
  }, [pending, api]);
}

/** Put inside a `<Link>` (pagination): while that link's navigation is pending the list counts as loading. */
export function LinkBusy() {
  const { pending } = useLinkStatus();
  useReportBusy(pending);
  return null;
}

/** The results column. Dimmed, with a bar across its top, while a new list is loading; the cards stay clickable. */
export function ResultsRegion({ className, children, ...rest }: React.HTMLAttributes<HTMLElement>) {
  const busy = useContext(BusyNow);
  return (
    <section aria-busy={busy || undefined} data-busy={busy || undefined} className={cn('relative', className, busy && 'opacity-50 transition-opacity duration-dg')} {...rest}>
      {busy && <div aria-hidden="true" className="absolute inset-x-0 -top-2 z-10 h-1 rounded-pill bg-primary motion-safe:animate-pulse" />}
      {children}
    </section>
  );
}
