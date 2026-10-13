import type { Metadata } from 'next';
import { ArrowRight, BellRing, Bookmark, Clock, GitCompare } from 'lucide-react';
import { buildMetadata } from '@/lib/seo';
import { getAccountStatus } from '@/lib/account';
import { BenefitGrid, Callout } from '@/components/dg/blocks';
import { Button } from '@/components/dg/button';
import { ContentPage } from '@/components/dg/content-page';
import { WaitlistForm } from '@/components/landing/waitlist-form';

export const revalidate = 60;

export const metadata: Metadata = buildMetadata({
  title: 'Alerts and saved searches',
  description: 'Save a search, follow buyers and programmes, and get an e-mail when new notices match. Changes to the notices you follow show on your dashboard.',
  path: '/alerts',
});

const FEATURES = [
  { icon: Bookmark, title: 'Saved searches', body: 'Save a search by country, buyer, product code or keyword and come back to it with one click. Alert e-mails list the new notices and calls that match it.' },
  { icon: GitCompare, title: 'Changes on your dashboard', body: 'Your dashboard shows what changed since your last visit in the notices you shortlisted and in those of buyers you follow: a moved deadline, a corrected value, a new status. Funding calls have no change history yet.' },
  { icon: Clock, title: 'Your cadence', body: 'Choose within the hour, a daily digest or a weekly summary, and pause an alert whenever you like.' },
  { icon: BellRing, title: 'Closing soon', body: 'Your dashboard lists the deadlines of the notices you shortlisted, and of your saved-search matches, for the next 14 days.' },
];

export default async function AlertsPage() {
  const { open } = await getAccountStatus();
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Alerts', href: '/alerts' }]}
      title="Alerts and saved searches"
      lead={open
        ? 'Stop re-checking portals. Sign in with your e-mail to save searches, follow buyers and get alerts.'
        : 'Stop re-checking portals. Saved searches and alerts are being prepared and are not open yet. There is no date.'}
    >
      {open && <Button href="/signin" iconRight={ArrowRight} className="self-start">Sign in with e-mail</Button>}

      <section aria-labelledby="features" className="flex flex-col gap-4">
        <h2 id="features" className="m-0 text-h2">{open ? 'What you get' : 'What is planned'}</h2>
        <BenefitGrid items={FEATURES} columns={2} />
      </section>

      <Callout title="Good to know">
        <p className="m-0">Browsing tenders, buyers and funding calls is free and needs no account. Alerts are best effort and do not replace checking the original notice. Sign-in is by a one-time link sent to your e-mail: there is no password.</p>
      </Callout>

      {!open && (
        <section aria-labelledby="waitlist" className="flex max-w-[860px] flex-col gap-3">
          <h2 id="waitlist" className="m-0 text-h2">Waitlist</h2>
          <p className="m-0 text-body text-ink-muted">The waitlist is not open. The form below checks your answers but stores and sends nothing, and we will not contact you.</p>
          <WaitlistForm />
        </section>
      )}
    </ContentPage>
  );
}
