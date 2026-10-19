'use client';

import Link, { useLinkStatus } from 'next/link';
import { LoaderCircle } from 'lucide-react';
import { Icon } from './icon';

/** Inside a `<Link>`: a spinner (and "Opening" for a screen reader) from the click until the next page is there. */
function Pending() {
  const { pending } = useLinkStatus();
  if (!pending) return null;
  return (
    <>
      <Icon icon={LoaderCircle} size="inline" data-link-pending="" className="ml-2 inline-block align-[-2px] motion-safe:animate-spin" />
      <span role="status" className="sr-only">Opening</span>
    </>
  );
}

/**
 * A card's link. `title` is the whole title for a card that clips it (a hover tooltip; the link text itself is never shortened). Not prefetched: the prefetch of a dynamic page is only its layout shell (214 bytes, measured), so twenty cards
 * on a list sent forty requests that warmed nothing. The click shows at once that it was taken (WP-49): the spinner here and
 * the card dimmed (`has-[[data-link-pending]]` on the card), instead of a list that looks dead for the 0.3 to 1.5 s the page takes.
 */
export function CardLink({ href, className, title, children }: { href: string; className?: string; title?: string; children: React.ReactNode }) {
  return <Link href={href} prefetch={false} className={className} title={title}>{children}<Pending /></Link>;
}
