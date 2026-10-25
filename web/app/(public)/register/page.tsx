import { permanentRedirect } from 'next/navigation';

export const dynamic = 'force-dynamic';

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

/** WP-123: registration moved to /signup (the pricing page links there); the old address keeps working, with its query. */
export default async function RegisterPage({ searchParams }: Props) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(await searchParams)) {
    if ((k === 'plan' || k === 'billing') && typeof v === 'string') q.set(k, v.slice(0, 20));
  }
  const s = q.toString();
  permanentRedirect(s ? `/signup?${s}` : '/signup');
}
