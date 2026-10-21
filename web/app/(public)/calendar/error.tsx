'use client';

import { ErrorState } from '@/components/dg/feedback';

/** Neither the tender nor the funding service answered (the page answers 503 at the edge). */
export default function CalendarError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <ErrorState title="We could not load the calendar" onRetry={reset}>
      The tender and funding services did not answer. Try again in a few minutes.
    </ErrorState>
  );
}
