'use client';

import { useSearchParams } from 'next/navigation';
import { ErrorState } from '@/components/dg/feedback';
import { TenderFilterBar } from '@/components/tenders/filter-bars';
import { parseTenderFilters } from '@/lib/filters';

/**
 * The list could not be had (the API took too long: 503). The heading and the filter panel stay, filled from
 * the address bar, so a visitor can narrow the request instead of starting over.
 */
export default function TendersError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const params = useSearchParams();
  const query: Record<string, string | string[]> = {};
  for (const key of new Set(params.keys())) {
    const all = params.getAll(key);
    query[key] = all.length === 1 ? all[0] : all;
  }
  return (
    <>
      <h1 className="m-0 page-title">Tenders</h1>
      <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <TenderFilterBar filters={parseTenderFilters(query)} basePath="/tenders" />
        <ErrorState title="We could not load tenders" onRetry={reset}>
          The data service is busy or slow at the moment. Your filters are kept: try again in a minute, or narrow them
          with a country or a deadline range.
        </ErrorState>
      </div>
    </>
  );
}
