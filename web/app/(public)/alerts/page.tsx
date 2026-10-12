import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { ContentPage } from '@/components/dg/content-page';
import { WaitlistForm } from '@/components/landing/waitlist-form';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Get alerts',
  description: 'Alerts for funding calls and tenders are planned. Sign-ups are not open yet.',
  path: '/alerts',
  // Placeholder text: not indexed until the page is written.
  noindex: true,
});

export default function AlertsPage() {
  return (
    <ContentPage
      draft
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Get alerts', href: '/alerts' }]}
      title="Get alerts"
      lead="Alerts for funding calls and tenders are planned. Sign-ups are not open yet."
    >
      <h2 className="m-0 text-h2">Join the waitlist</h2>
      <p className="m-0 text-body text-ink-muted">
        The form below checks your answers, but nothing is stored or sent. We will not contact you.
      </p>
      <WaitlistForm />
    </ContentPage>
  );
}
