'use client';

import { ErrorState } from '@/components/dg/feedback';

export default function MarketError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState title="We could not load the market overview" onRetry={reset} />;
}
