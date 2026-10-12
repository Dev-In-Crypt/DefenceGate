'use client';

import { ErrorState } from '@/components/dg/feedback';

export default function FundingError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState title="We could not load funding calls" onRetry={reset} />;
}
