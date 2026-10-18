import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { ContentPage } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Pricing',
  description: 'Pricing is not announced. Browsing DefenceGate is free today; anything beyond that will be announced with its terms before it is offered.',
  path: '/pricing',
  noindex: true,
});

/** No prices, limits or promises: only what is true today. */
const PLANS: { name: string; price: string; status: string; note: string }[] = [
  { name: 'Browsing', price: 'Free today', status: 'Available', note: 'Funding calls, tenders, buyers and source status.' },
  { name: 'Alerts', price: 'Not announced', status: 'Not available yet', note: 'Planned. Sign-ups are not open.' },
  { name: 'Opportunity pack', price: 'Not announced', status: 'Not available yet', note: 'Planned. Orders are not open.' },
  { name: 'Pro archive', price: 'Not announced', status: 'Not available yet', note: 'Planned. Scope is not defined.' },
];

export default function PricingPage() {
  return (
    <ContentPage
      wide
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Pricing', href: '/pricing' }]}
      title="Pricing"
      lead="Pricing is not announced. Browsing is free today. Anything beyond that will be announced with its terms before it is offered."
    >
      <ul className="m-0 grid list-none gap-4 p-0 md:grid-cols-2 xl:grid-cols-4">
        {PLANS.map((p) => (
          <li key={p.name} className="min-w-0">
            <article className="flex h-full flex-col gap-4 rounded-lg border border-edge bg-surface p-5 sm:p-6">
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
    </ContentPage>
  );
}
