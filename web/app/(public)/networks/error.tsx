'use client';

import { ErrorState } from '@/components/dg/feedback';

/** The data service did not answer for a network list (the page answers 503 at the edge). */
export default function NetworksError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState title="This list could not be loaded" onRetry={reset}>The data service did not answer. Try again in a few minutes.</ErrorState>;
}
