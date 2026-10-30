import type { Metadata } from 'next';
import Link from 'next/link';
import { getEligibilityCalls, getUserState } from '@/lib/account';
import { absoluteUrl } from '@/lib/seo';
import { EligibilityPack } from '@/components/account/eligibility-pack';
import { AppHeader, Block, LoadFailed } from '@/components/account/ui';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Eligibility pack', robots: { index: false, follow: false } };

/**
 * WP-156: the eligibility check's results pack, part of Pro and up (`eligibility_export`; while no plan is on sale, every account's). The
 * open calls and their facts come from the API (/v1/account/eligibility/calls, refused without the feature); the profile and the verdicts
 * stay in the browser (components/account/eligibility-pack.tsx).
 */
export default async function EligibilityPage() {
  const state = await getUserState();
  const lead = 'Every open call your saved profile fits, with its verdict, each rule with the sentence it was read from and the links: to print, save as PDF or download as CSV.';
  if (state.kind === 'ok' && !state.user.features.includes('eligibility_export')) {
    return (
      <>
        <AppHeader title="Eligibility pack" lead={lead} />
        <Block id="plan" title="Part of a paid plan">
          <p className="m-0 max-w-prose text-body text-ink-muted" data-pack-plan>
            The eligibility pack is part of the Pro, Team and Consultant plans: see <Link href="/app/billing" className="font-semibold">Billing</Link>.
            The check itself stays free: <Link href="/readiness/results" className="font-semibold">your readiness results</Link>.
          </p>
        </Block>
      </>
    );
  }
  const r = await getEligibilityCalls();
  if (!r.ok) return <LoadFailed href="/app/eligibility" />;
  return (
    <>
      <AppHeader title="Eligibility pack" lead={lead} />
      <EligibilityPack answer={r.data} base={absoluteUrl('').replace(/\/$/, '')} />
    </>
  );
}
