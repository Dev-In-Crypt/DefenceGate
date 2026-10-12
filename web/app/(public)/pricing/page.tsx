import type { Metadata } from 'next';
import { Bell } from 'lucide-react';
import { buildMetadata } from '@/lib/seo';
import { Button } from '@/components/dg/button';
import { ContentPage, Placeholder } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Pricing',
  description: 'Plans and prices for DefenceGate are not announced yet.',
  path: '/pricing',
  noindex: true,
});

/** No prices, limits or promises: only what is true today. */
const PLANS: { name: string; price: string; status: string; note: string }[] = [
  { name: 'Directory', price: 'Free today', status: 'Available', note: 'Funding calls, tenders, buyers and source status. Future terms are to be announced.' },
  { name: 'Alerts', price: 'To be announced', status: 'Not available yet', note: 'Planned. Sign-ups are not open.' },
  { name: 'Opportunity pack', price: 'To be announced', status: 'Not available yet', note: 'Planned. Orders are not open.' },
  { name: 'Pro archive', price: 'To be announced', status: 'Not available yet', note: 'Planned. Scope is not defined.' },
];

export default function PricingPage() {
  return (
    <ContentPage
      draft
      wide
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Pricing', href: '/pricing' }]}
      title="Pricing"
      lead="Prices and limits are not announced yet. Nothing on this page is an offer."
    >
      <ul className="m-0 grid list-none gap-4 p-0 md:grid-cols-2 xl:grid-cols-4">
        {PLANS.map((p) => (
          <li key={p.name} className="min-w-0">
            <article className="flex h-full flex-col gap-4 rounded-lg bg-surface p-5 sm:p-6">
              <h2 className="m-0 text-h3">{p.name}</h2>
              <div className="flex flex-col gap-1 rounded-md bg-surface-inset p-4">
                <span className="text-label text-ink-muted">Price</span>
                <span className="font-mono text-mono-strong">{p.price}</span>
              </div>
              <p className="m-0 text-small font-bold">{p.status}</p>
              <p className="m-0 text-body text-ink-muted">{p.note}</p>
            </article>
          </li>
        ))}
      </ul>
      <p className="m-0 text-body text-ink-muted">Limits, billing and terms: <Placeholder>to be announced</Placeholder></p>
      <Button href="/alerts" variant="secondary" icon={Bell} className="self-start">Join the waitlist</Button>
    </ContentPage>
  );
}
