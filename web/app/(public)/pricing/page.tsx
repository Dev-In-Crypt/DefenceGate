import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { ContentPage } from '@/components/dg/content-page';
import { Card } from '@/components/dg/card';
import { DataTable } from '@/components/dg/data-table';

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
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Pricing', href: '/pricing' }]}
      title="Pricing"
      lead="Pricing is not announced. Browsing is free today. Anything beyond that will be announced with its terms before it is offered."
    >
      {/* One table, not four cards of which three said "Not announced". */}
      <Card>
        <DataTable label="Plans, prices and status" minWidth={560}>
          <thead>
            <tr><th scope="col">Plan</th><th scope="col">Price</th><th scope="col">Status</th><th scope="col">Note</th></tr>
          </thead>
          <tbody>
            {PLANS.map((p) => (
              <tr key={p.name}>
                <th scope="row" className="whitespace-nowrap">{p.name}</th>
                <td className="whitespace-nowrap font-mono">{p.price}</td>
                <td className="whitespace-nowrap font-bold">{p.status}</td>
                <td className="text-ink-muted">{p.note}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </Card>
    </ContentPage>
  );
}
