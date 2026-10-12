import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { ContentPage, ContentSection, PendingSections, Placeholder } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Privacy',
  description: 'How DefenceGate handles personal data. Draft: the text is not written yet.',
  path: '/privacy',
  // Skeleton without final text: not indexed until the text exists.
  noindex: true,
});

export default function PrivacyPage() {
  return (
    <ContentPage
      draft
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Privacy', href: '/privacy' }]}
      title="Privacy"
      lead="This page will describe how personal data is handled. The facts below are the ones we can state today."
    >
      <ContentSection title="Who is responsible">
        <p className="m-0 text-body text-ink-muted">Controller and contact: <Placeholder>to be provided</Placeholder></p>
      </ContentSection>

      <ContentSection title="What this site stores about you">
        <ul className="m-0 flex list-disc flex-col gap-1 pl-6 text-body text-ink-muted">
          <li>There are no accounts and no sign-in.</li>
          <li>There is no analytics and no advertising.</li>
          <li>The site sets no cookies of its own.</li>
          <li>Your light or dark theme choice is kept in your browser&apos;s local storage, on your device.</li>
          <li>The waitlist form does not store or send what you enter. Sign-ups are not open.</li>
        </ul>
      </ContentSection>

      <ContentSection title="Server logs">
        <p className="m-0 text-body text-ink-muted">What the host keeps when you load a page: <Placeholder>to be described</Placeholder></p>
      </ContentSection>

      <PendingSections items={[
        { title: 'Purposes and legal basis' },
        { title: 'Who receives data' },
        { title: 'How long data is kept' },
        { title: 'Your rights' },
        { title: 'Contact and complaints' },
      ]} />
    </ContentPage>
  );
}
