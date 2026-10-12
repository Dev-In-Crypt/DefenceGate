'use client';

import { ErrorState } from '@/components/dg/feedback';

export default function TendersError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState title="We could not load tenders" onRetry={reset} />;
}
