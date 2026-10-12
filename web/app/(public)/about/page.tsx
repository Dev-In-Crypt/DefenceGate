import type { Metadata } from 'next';
import Link from 'next/link';
import { buildMetadata } from '@/lib/seo';
import { ContentPage, ContentSection, Placeholder } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'About DefenceGate',
  description: 'What DefenceGate is and where its data comes from. Draft: the text is not written yet.',
  path: '/about',
  noindex: true,
});

export default function AboutPage() {
  return (
    <ContentPage
      draft
      crumbs={[{ label: 'Home', href: '/' }, { label: 'About', href: '/about' }]}
      title="About DefenceGate"
      lead="Defence and dual-use funding calls and tenders from EU and national portals, in one English feed."
    >
      <ContentSection title="What it is">
        <p className="m-0 text-body text-ink-muted">
          DefenceGate collects funding calls and tenders from public portals every day and shows each one with its source, licence and the time it was retrieved.
        </p>
      </ContentSection>

      <ContentSection title="Where the data comes from">
        <p className="m-0 text-body text-ink-muted">
          Every source, when it last ran and how complete the run was is listed on the <Link href="/data" className="font-semibold">source status page</Link>.
        </p>
      </ContentSection>

      <ContentSection title="Who runs it">
        <p className="m-0 text-body text-ink-muted"><Placeholder>to be provided</Placeholder></p>
      </ContentSection>

      <ContentSection title="Contact">
        <p className="m-0 text-body text-ink-muted"><Placeholder>to be provided</Placeholder></p>
      </ContentSection>
    </ContentPage>
  );
}
