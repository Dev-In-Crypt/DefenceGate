import Link from 'next/link';
import { alsoSearchedLine } from '@/lib/search-terms';
import type { CpvHint } from '@/lib/types';

/**
 * WP-110 (p01: "wiring harness" listed a canteen and a concrete foundation, with no word of CPV 31611000): the codes the words
 * name, said beside the results whatever they are: "Did you mean CPV 31611000 Wiring sets?", each a link to the list by that code.
 */
export function CpvHints({ hints, hrefFor }: { hints?: CpvHint[]; hrefFor: (prefix: string) => string }) {
  if (!hints?.length) return null;
  return (
    <p className="m-0 max-w-prose text-small text-ink-muted" data-cpv-hints>
      Did you mean{' '}
      {hints.map((h, i) => (
        <span key={h.code}>
          {i > 0 && (i === hints.length - 1 ? ' or ' : ', ')}
          <Link href={hrefFor(h.prefix)} className="font-semibold">CPV {h.code} {h.title}</Link>
        </span>
      ))}
      ? A code finds the notices whatever words their titles use.
    </p>
  );
}

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
