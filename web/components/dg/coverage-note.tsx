import Link from 'next/link';
import { countedLine, coverageLines } from '@/lib/coverage-copy';

/** WP-98b: what we collect for the chosen countries, one line each, with the way to the source list. Nothing without a country. */
export function CoverageNote({ countries, kind = 'tenders', counted }: { countries: string[] | undefined; kind?: 'tenders' | 'awards'; counted?: string[] }) {
  // WP-112: one country and the sources its count holds (/market): the line names those sources
  const one = (countries ?? []).filter((c) => c && c !== 'EU');
  const lines = counted && one.length === 1 ? [`${countedLine(one[0], counted)}.`] : coverageLines(countries, kind);
  if (lines.length === 0) return null;
  return (
    <p className="m-0 max-w-prose text-small text-ink-muted" data-coverage-note>
      {lines.join(' ')} <Link href="/data" className="font-semibold">Sources we collect</Link>
    </p>
  );
}
