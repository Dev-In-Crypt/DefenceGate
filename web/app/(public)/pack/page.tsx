import type { Metadata } from 'next';
import { Bell } from 'lucide-react';
import { buildMetadata } from '@/lib/seo';
import { Button } from '@/components/dg/button';
import { ComingSoon } from '@/components/dg/feedback';
import { ContentPage, ContentSection, Placeholder } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Opportunity pack',
  description: 'The opportunity pack is planned and not available yet.',
  path: '/pack',
  noindex: true,
});

export default function PackPage() {
  return (
    <ContentPage
      draft
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Opportunity pack', href: '/pack' }]}
      title="Opportunity pack"
      lead="A report on the opportunities that fit a specific company. It is planned and is not available yet."
    >
      <ContentSection title="Availability">
        <ComingSoon feature="Opportunity pack" />
        <p className="m-0 text-body text-ink-muted">
          Orders are not open. You cannot buy or request a pack today.
        </p>
        <Button href="/alerts" variant="secondary" icon={Bell} className="self-start">Join the waitlist</Button>
      </ContentSection>

      <ContentSection title="What it will contain">
        <ul className="m-0 flex list-disc flex-col gap-1 pl-6 text-body text-ink-muted">
          <li>Open tenders and funding calls that match the company profile.</li>
          <li><Placeholder>further contents to be defined</Placeholder></li>
        </ul>
      </ContentSection>

      <ContentSection title="Who it is for">
        <p className="m-0 text-body text-ink-muted">
          Manufacturers with 20 to 500 staff who want to supply European defence and dual-use programmes.
        </p>
      </ContentSection>

      <ContentSection title="Price and delivery">
        <p className="m-0 text-body text-ink-muted"><Placeholder>to be announced</Placeholder></p>
      </ContentSection>
    </ContentPage>
  );
}
