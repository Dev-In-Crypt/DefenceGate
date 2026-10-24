'use client';

import { useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ErrorState } from '@/components/dg/feedback';
import { TenderFilterBar } from '@/components/tenders/filter-bars';
import { parseTenderFilters } from '@/lib/filters';

/**
 * The list could not be had (the API took too long: 503). The heading and the filter panel stay, filled from
 * the address bar, so a visitor can narrow the request instead of starting over. Never the empty list: a failed read is not
 * "no tenders match" (WP-101). "Try again" reads the list again from the server (`router.refresh`): `reset` alone re-renders
 * the error the server already sent.
 */
export default function TendersError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const params = useSearchParams();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const retry = () => startTransition(() => { router.refresh(); reset(); });
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
        <ErrorState title="We could not load tenders" onRetry={pending ? undefined : retry}>
          The data service is busy or slow at the moment. Your filters are kept: try again in a minute, or narrow them
          with a country or a deadline range.
        </ErrorState>
      </div>
    </>
  );
}
