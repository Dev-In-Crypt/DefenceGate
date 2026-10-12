'use client';

import { ErrorState } from '@/components/dg/feedback';

export default function DataError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState title="We could not load the source status" onRetry={reset} />;
}
