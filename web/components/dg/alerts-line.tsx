'use client';

import Link from 'next/link';
import { useAccountsOpen } from '@/components/account/accounts-open';

/**
 * One quiet line on a detail page. It links to /alerts only while accounts are open (the public layout's status, cached
 * for 60 seconds, where any failure reads as "not open"); otherwise nothing is rendered: no "Coming soon" boxes.
 * WP-142: it reads the layout's status, not the service: an async component is a part of the page that arrives on its own,
 * and the browser's hydration of a document still arriving failed on one (the footer, React error #418: components/dg/footer.tsx).
 */
export function AlertsLine() {
  const open = useAccountsOpen();
  if (!open) return null;
  return (
    <p className="m-0 text-small text-ink-muted">
      To hear about new notices and calls that match a search, <Link href="/alerts" className="font-semibold">set up an alert</Link>.
    </p>
  );
}
