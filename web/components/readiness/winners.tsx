'use client';

import { useEffect, useState } from 'react';
import { DEMAND_FAILED, DemandError, demandRequest, fetchWinners, type WinnersPage } from '@/lib/demand';
import { formatDateUtc } from '@/lib/format';
import { countryName } from '@/lib/taxonomy';
import { Button } from '@/components/dg/button';
import { AboutData } from '@/components/dg/about-data';
import { ErrorState, Skeleton } from '@/components/dg/feedback';
import { Winner, winnersScope } from './approach';
import { useProfile } from './use-readiness';

type State = { state: 'loading' } | { state: 'error'; message: string } | { state: 'done'; data: WinnersPage };

/**
 * WP-81: every winner of the demand answer for the profile's CPV codes, in the order and form of "who to approach", a page at a time.
 * `?country=ES` narrows it to one of the five countries. Built in the browser from the stored profile; the server keeps nothing.
 */
export function AllWinners() {
  const { profile } = useProfile();
  const [page, setPage] = useState(1);
  const [country, setCountry] = useState<string | null | undefined>(undefined);
  const [result, setResult] = useState<State>({ state: 'loading' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => { setCountry(new URLSearchParams(window.location.search).get('country')); }, []);
  const base = profile ? demandRequest(profile) : null;
  const request = base && country !== undefined
    ? { ...base, countries: country && base.countries.includes(country) ? [country] : base.countries, page } : null;
  const key = request ? JSON.stringify(request) : '';
  useEffect(() => {
    if (!key) return;
    const controller = new AbortController();
    setResult({ state: 'loading' });
    fetchWinners(JSON.parse(key), controller.signal).then(
      (data) => { if (!controller.signal.aborted) setResult({ state: 'done', data }); },
      (e: unknown) => { if (!controller.signal.aborted) setResult({ state: 'error', message: e instanceof DemandError ? e.message : DEMAND_FAILED }); },
    );
    return () => controller.abort();
  }, [key, attempt]);

  if (profile && !base) {
    return (
      <div className="flex flex-col gap-3">
        <p className="m-0 text-body">Choose the CPV codes of what you make on your supplier profile, and this page lists every company that wins those contracts.</p>
        <div><Button href="/readiness/supplier" variant="secondary">Add CPV codes to my supplier profile</Button></div>
      </div>
    );
  }
  if (result.state === 'loading') return <div role="status" aria-label="Finding who wins these contracts"><Skeleton className="h-40" /></div>;
  if (result.state === 'error') return <ErrorState title="The list could not be computed" onRetry={() => setAttempt((n) => n + 1)}>{result.message}</ErrorState>;
  const d = result.data;
  const last = Math.max(1, Math.ceil(d.total / d.pageSize));
  const from = d.total === 0 ? 0 : (d.page - 1) * d.pageSize + 1;
  return (
    <div className="flex flex-col gap-4" data-all-winners>
      <p className="m-0 max-w-prose text-body" data-all-winners-summary>
        From {formatDateUtc(d.since)} to {formatDateUtc(d.until)}, in {d.countries.map(countryName).join(', ')}: {d.total}{' '}
        {d.total === 1 ? 'company' : 'companies'} won defence-scope procurements under your codes, every one named here, most contracts first
        {d.total > 0 ? ` (${from} to ${Math.min(d.page * d.pageSize, d.total)} on this page)` : ''}. A winner who is a natural person is never named.
      </p>
      <ul className="m-0 flex list-none flex-col p-0">
        {d.winners.map((w, i) => <Winner key={`${d.page}-${i}-${w.name}`} w={w} scope={winnersScope(d)} request={request} />)}
      </ul>
      {last > 1 && (
        <nav aria-label="Pages of winners" className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" disabled={d.page <= 1} onClick={() => setPage(d.page - 1)}>Previous page</Button>
          <span className="text-small text-ink-muted">Page {d.page} of {last}</span>
          <Button variant="secondary" disabled={d.page >= last} onClick={() => setPage(d.page + 1)}>Next page</Button>
        </nav>
      )}
      <AboutData summary="Where the winners come from"><p className="m-0">{d.winnersFrom}</p></AboutData>
      <div><Button href="/readiness/supplier/report#r-approach" variant="secondary">Back to the supplier report</Button></div>
    </div>
  );
}
