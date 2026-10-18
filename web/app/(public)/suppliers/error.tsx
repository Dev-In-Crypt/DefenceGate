'use client';

import { ErrorState } from '@/components/dg/feedback';

export default function SuppliersError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState title="We could not load the supplier map" onRetry={reset} />;
}
