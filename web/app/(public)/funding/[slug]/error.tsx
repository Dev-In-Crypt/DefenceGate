'use client';

import { ErrorState } from '@/components/dg/feedback';

export default function CallError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState title="We could not load this call" onRetry={reset} />;
}
