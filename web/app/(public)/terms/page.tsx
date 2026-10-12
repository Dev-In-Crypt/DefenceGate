import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { ContentPage, PendingSections } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Terms',
  description: 'Terms of use for DefenceGate. Draft: the text is not written yet.',
  path: '/terms',
  noindex: true,
});

export default function TermsPage() {
  return (
    <ContentPage
      draft
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Terms', href: '/terms' }]}
      title="Terms"
      lead="The terms of use are not written yet. This page shows the headings they will have."
    >
      <PendingSections items={[
        { title: 'Who provides the service' },
        { title: 'What the service is' },
        { title: 'Source data and licences' },
        { title: 'Accuracy and no warranty' },
        { title: 'Acceptable use' },
        { title: 'Liability' },
        { title: 'Changes to these terms' },
        { title: 'Governing law' },
        { title: 'Contact' },
      ]} />
    </ContentPage>
  );
}
