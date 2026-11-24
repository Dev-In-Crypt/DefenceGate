'use client';

import { usePathname } from 'next/navigation';
import { ErrorState } from '@/components/dg/feedback';

/** E-29: one boundary for the map, a company, its competitors and its report: the title names what failed to load. */
export default function SuppliersError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const path = usePathname() ?? '';
  const what = path.endsWith('/report') ? 'this company report' : path.endsWith('/competitors') ? 'this competitor list'
    : /^\/suppliers\/[^/]+$/.test(path) ? 'this company' : 'the supplier map';
  return <ErrorState title={`We could not load ${what}`} onRetry={reset} />;
}
