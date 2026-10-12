import type { Metadata } from 'next';
import { Bell } from 'lucide-react';
import { buildMetadata } from '@/lib/seo';
import { Button } from '@/components/dg/button';
import { ComingSoon } from '@/components/dg/feedback';
import { Callout, ClauseList } from '@/components/dg/blocks';
import { ContentPage, ContentSection } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Opportunity pack',
  description: 'The opportunity pack is a planned report on the open tenders and funding calls that fit one company. It is not available yet.',
  path: '/pack',
  noindex: true,
});

export default function PackPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Opportunity pack', href: '/pack' }]}
      title="Opportunity pack"
      lead="A report assembled for one company: the open opportunities that fit it, in one document, each with its source."
    >
      <ContentSection title="Status">
        <ComingSoon feature="Opportunity pack" />
        <p className="m-0 text-body text-ink-muted">
          The pack is planned. It cannot be ordered today and we do not give a date or a price.
        </p>
        <Button href="/alerts" variant="secondary" icon={Bell} className="self-start">What is planned for alerts</Button>
      </ContentSection>

      <ContentSection title="What it is meant to contain">
        <ClauseList items={[
          'The open tenders and funding calls that match a company profile.',
          'The buyers behind them and their other current notices.',
          'The deadlines, in one list, with a link to the source of every item.',
        ]} />
      </ContentSection>

      <Callout title="What it will not be">
        <p className="m-0">Not a guarantee of fit, eligibility or success, and not legal or bidding advice. The contents may change before it is offered.</p>
      </Callout>
    </ContentPage>
  );
}
