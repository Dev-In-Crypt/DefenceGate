import Link from 'next/link';
import { getAccountStatus } from '@/lib/account';

/**
 * One quiet line on a detail page. It links to /alerts only while accounts are open (the status call is cached
 * for 60 seconds and any failure reads as "not open"); otherwise nothing is rendered: no "Coming soon" boxes.
 */
export async function AlertsLine() {
  const { open } = await getAccountStatus();
  if (!open) return null;
  return (
    <p className="m-0 text-small text-ink-muted">
      To hear about new notices and calls that match a search, <Link href="/alerts" className="font-semibold">set up an alert</Link>.
    </p>
  );
}
