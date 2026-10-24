import Link from 'next/link';
import { coverageLines } from '@/lib/coverage-copy';

/** WP-98b: what we collect for the chosen countries, one line each, with the way to the source list. Nothing without a country. */
export function CoverageNote({ countries, kind = 'tenders' }: { countries: string[] | undefined; kind?: 'tenders' | 'awards' }) {
  const lines = coverageLines(countries, kind);
  if (lines.length === 0) return null;
  return (
    <p className="m-0 max-w-prose text-small text-ink-muted" data-coverage-note>
      {lines.join(' ')} <Link href="/data" className="font-semibold">Sources we collect</Link>
    </p>
  );
}
