'use client';

import { ErrorState } from '@/components/dg/feedback';

export default function BuyerError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState title="We could not load this buyer" onRetry={reset} />;
}
