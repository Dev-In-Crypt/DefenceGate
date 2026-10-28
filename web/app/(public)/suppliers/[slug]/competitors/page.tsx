import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getSupplier, getSupplierCompetition, isSupplierSlug, REMOVED, whenRemoved } from '@/lib/api';
import { getFullCompetition, getUserState } from '@/lib/account';
import { displayName } from '@/lib/display-name';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { RemovedOnRequest } from '@/components/dg/removed';
import { CompetitorsCard } from '@/components/dg/competition';
import { companyCrumbs } from '@/components/dg/companies-tabs';

/**
 * WP-155 (owner, mosaic rule): a company's whole competitor list. The supplier page names the first five to everyone; the rest is for a
 * signed-in account whose plan has `competitors_full` (Pro and up; every account while no plan is on sale), as the account API decides.
 */
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Competitors', robots: { index: false, follow: false } };

type Props = { params: Promise<{ slug: string }> };

export default async function CompetitorsPage({ params }: Props) {
  const { slug } = await params;
  if (!isSupplierSlug(slug)) notFound();
  const [got, pub] = await Promise.all([getSupplier(slug).catch(whenRemoved), getSupplierCompetition(slug).catch(() => null)]);
  if (got === REMOVED) return <RemovedOnRequest what="supplier" />;
  if (!got || !pub) notFound();
  const s = { ...got, name: displayName(got.name, 'title') };
  const state = await getUserState();
  let c = pub;
  let gate: React.ReactNode = null;
  if (state.kind === 'anonymous' || state.kind === 'unauthorized') {
    gate = <>The full list of competitors is for signed-in accounts: <Link href={`/signin?next=/suppliers/${s.slug}/competitors`} className="font-semibold">sign in</Link>.</>;
  } else if (state.kind === 'unavailable') {
    gate = <>Your account could not be read just now. Try again in a moment.</>;
  } else {
    const full = await getFullCompetition(s.slug);
    if (full.ok) c = full.data;
    else if (full.status === 402) gate = <span data-competitors-plan>The full list of competitors comes with the Pro, Team and Consultant plans: see <Link href="/app/billing" className="font-semibold">Billing</Link> in your account.</span>;
    else gate = <>The full list could not be read just now. Try again in a moment.</>;
  }
  return (
    <>
      <PageHeader crumbs={[...companyCrumbs('suppliers'), { label: s.name, href: `/suppliers/${s.slug}` }, { label: 'Competitors', href: `/suppliers/${s.slug}/competitors` }]}
        title={`Competitors of ${s.name}`} />
      {gate && <Card><p className="m-0 text-body" data-competitors-gate>{gate}</p></Card>}
      {c.available
        ? <CompetitorsCard c={c} name={s.name} />
        : <Card><p className="m-0 text-body">The figures are being renewed. Try again in a few minutes.</p></Card>}
    </>
  );
}
