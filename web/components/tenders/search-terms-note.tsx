import Link from 'next/link';
import { alsoSearchedLine } from '@/lib/search-terms';

/** WP-98: the terms of other languages a tender search was also read as (lib/data/search-terms.json), said under the count. */
export function AlsoSearched({ also }: { also?: string[] }) {
  const line = alsoSearchedLine(also);
  return line ? <p className="m-0 max-w-prose text-small text-ink-muted" data-also-searched>{line}</p> : null;
}

/** WP-98: with nothing found, the product codes of the groups the words belong to, as a link to the same list by code. */
export function GroupSuggestions({ groups, hrefFor }: {
  groups?: { id: string; label: string; cpv: string[] }[]; hrefFor: (cpv: string[]) => string;
}) {
  if (!groups?.length) return null;
  return (
    <span className="mt-2 flex flex-col gap-1" data-search-suggestion>
      {groups.map((g) => (
        <Link key={g.id} href={hrefFor(g.cpv)} className="font-semibold">
          Tenders under the product codes of {g.label} (CPV {g.cpv.join(', ')})
        </Link>
      ))}
    </span>
  );
}
