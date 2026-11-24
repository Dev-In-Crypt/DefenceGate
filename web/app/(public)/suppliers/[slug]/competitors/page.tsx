import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getSupplier, getSupplierCompetition, isSupplierSlug, REMOVED, whenRemoved } from '@/lib/api';
import { getAccountStatus, getFullCompetition, getUserState } from '@/lib/account';
import { PLANS_FROM } from '@/lib/plans';
import { displayName } from '@/lib/display-name';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { RemovedOnRequest } from '@/components/dg/removed';
import { CompetitorsCard } from '@/components/dg/competition';
import { ShareNote } from '@/components/dg/share-note';
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
  // E-22 (F19): a gate only when the public answer leaves companies out, and it names who has the rest
  const hidden = pub.competitorCount > pub.competitors.length;
  if (state.kind === 'anonymous' || state.kind === 'unauthorized') {
    // WP-175 + WP-176 (F19, E-22): only when companies are left out; the first five are free, the rest is said as it is
    if (hidden) {
      const status = await getAccountStatus();
      const plans = `part of the ${PLANS_FROM.pro}`;
      gate = status.open
        ? <>The first five competitors are free on the <Link href={`/suppliers/${s.slug}`} className="font-semibold">company page</Link>. The full list is {status.plansOnSale ? plans : 'free to every account while no paid plan is on sale'}: <Link href={`/signin?next=/suppliers/${s.slug}/competitors`} className="font-semibold">sign in</Link>{status.plansOnSale && <> or see <Link href="/pricing" className="font-semibold">pricing</Link></>}.</>
        : <>The first five competitors are free on the <Link href={`/suppliers/${s.slug}`} className="font-semibold">company page</Link>. The full list will come with an account ({status.plansOnSale ? plans : `later ${plans}`}); accounts are not open yet.</>;
    }
  } else if (state.kind === 'unavailable') {
    gate = <>Your account could not be read just now. Try again in a moment.</>;
  } else {
    const full = await getFullCompetition(s.slug);
    if (full.ok) c = full.data;
    else if (full.status === 402) gate = hidden && <span data-competitors-plan>The full list of competitors is part of the {PLANS_FROM.pro}: see <Link href="/app/billing" className="font-semibold">Billing</Link> in your account.</span>;
    else gate = <>The full list could not be read just now. Try again in a moment.</>;
  }
  return (
    <>
      <PageHeader crumbs={[...companyCrumbs('suppliers'), { label: s.name, href: `/suppliers/${s.slug}` }, { label: 'Competitors', href: `/suppliers/${s.slug}/competitors` }]}
        title={`Competitors of ${s.name}`} />
      {gate && <Card><p className="m-0 text-body" data-competitors-gate>{gate}</p></Card>}
      {c.available
        ? <><CompetitorsCard c={c} name={s.name} /><ShareNote /></>
        : <Card><p className="m-0 text-body">The figures are being renewed. Try again in a few minutes.</p></Card>}
    </>
  );
}
