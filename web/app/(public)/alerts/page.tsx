import type { Metadata } from 'next';
import { BellRing, Bookmark, GitCompare, Clock } from 'lucide-react';
import { buildMetadata } from '@/lib/seo';
import { BenefitGrid, Callout } from '@/components/dg/blocks';
import { ContentPage } from '@/components/dg/content-page';
import { WaitlistForm } from '@/components/landing/waitlist-form';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Alerts',
  description: 'Alerts for tenders and funding calls are planned and not open yet. What is planned and how it will work.',
  path: '/alerts',
  // Nothing to find here until alerts are open.
  noindex: true,
});

const PLANNED = [
  { icon: Bookmark, title: 'Saved searches', body: 'Save a search by country, buyer, product code or keyword and come back to it with one click.' },
  { icon: GitCompare, title: 'Change alerts', body: 'Be told when a notice you follow changes: a moved deadline, a corrected value, a new status.' },
  { icon: Clock, title: 'Your cadence', body: 'Choose instant, a daily digest or a weekly summary, and pause an alert whenever you like.' },
  { icon: BellRing, title: 'Closing soon', body: 'A reminder before the deadlines of the notices you shortlisted.' },
];

export default function AlertsPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Alerts', href: '/alerts' }]}
      title="Alerts"
      lead="Stop re-checking portals. Alerts and a personal workspace are planned. They are not open yet and there is no date."
    >
      <section aria-labelledby="planned" className="flex flex-col gap-4">
        <h2 id="planned" className="m-0 text-h2">What is planned</h2>
        <BenefitGrid items={PLANNED} columns={2} />
      </section>

      <Callout title="Available today">
        <p className="m-0">Browsing tenders, buyers and funding calls is free and needs no account. Alerts are best effort and will not replace checking the source.</p>
      </Callout>

      <section aria-labelledby="waitlist" className="flex max-w-[860px] flex-col gap-3">
        <h2 id="waitlist" className="m-0 text-h2">Waitlist</h2>
        <p className="m-0 text-body text-ink-muted">The waitlist is not open. The form below checks your answers but stores and sends nothing, and we will not contact you.</p>
        <WaitlistForm />
      </section>
    </ContentPage>
  );
}
