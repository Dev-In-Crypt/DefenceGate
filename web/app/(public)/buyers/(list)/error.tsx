'use client';

import { ErrorState } from '@/components/dg/feedback';

export default function BuyersError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState title="We could not load buyers" onRetry={reset} />;
}
