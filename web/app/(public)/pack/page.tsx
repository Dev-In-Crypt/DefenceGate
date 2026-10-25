import type { Metadata } from 'next';
import { ArrowRight } from 'lucide-react';
import { buildMetadata } from '@/lib/seo';
import { Button } from '@/components/dg/button';
import { ClauseList } from '@/components/dg/blocks';
import { ContentPage, ContentSection } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Opportunity pack',
  description: 'A ready-made pack for one company is not offered. Put the same list together yourself, free: filters, CSV export, the readiness check and the calendar feed.',
  path: '/pack',
  noindex: true,
});

/** One block: what is not offered, and how to get the same list from what the site has today (owner decision, 21 October 2026). */
export default function PackPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Opportunity pack', href: '/pack' }]}
      title="Opportunity pack"
      lead="A pack of the open tenders and funding calls that fit one company, assembled for you, is not offered. You can put the same list together yourself today, free and without an account."
    >
      <ContentSection title="Put it together yourself">
        <ClauseList items={[
          'Filter the tenders by country, product code (CPV) or keyword, and the funding calls by programme, funder country or keyword. The filters are in the address, so a bookmark keeps the search.',
          'Download each result as CSV: the public fields, with the source, licence and attribution on every row.',
          'Run the readiness check to see which rules of the EU programmes (EDF, EDIP, SAFE), NATO supply and the Spanish Ministry of Defence route your company meets. Your answers are saved in your browser, not on our server; the check’s page lists what is sent to compute the result.',
          'Subscribe to the calendar feed for the deadlines, and to the Atom feed of what changed.',
        ]} />
        <h3 className="m-0 text-h4">What it is not</h3>
        <p className="m-0 text-body text-ink-muted">Not a guarantee of fit, eligibility or success, and not legal or bidding advice. Check every item against its original notice.</p>
        <div className="flex flex-wrap gap-3">
          <Button href="/tenders" iconRight={ArrowRight}>Tenders</Button>
          <Button href="/funding" variant="secondary">Funding calls</Button>
          <Button href="/readiness" variant="secondary">Readiness check</Button>
        </div>
      </ContentSection>
    </ContentPage>
  );
}
