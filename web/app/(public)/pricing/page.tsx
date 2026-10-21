import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { ContentPage } from '@/components/dg/content-page';
import { Card } from '@/components/dg/card';
import { DataTable } from '@/components/dg/data-table';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Pricing',
  description: 'DefenceGate is free to use and there is no paid plan. What it offers today: the lists, CSV export, Atom feeds, a calendar feed and the readiness check.',
  path: '/pricing',
  noindex: true,
});

/** What the site offers today and what it costs (owner decision, 21 October 2026): no prices, no dates, nothing that does not exist. */
const OFFER: { name: string; price: string; status: string; note: string }[] = [
  { name: 'Browsing', price: 'Free', status: 'Open', note: 'Tenders, funding calls, buyers, organisations and the source status, with no account.' },
  { name: 'CSV export', price: 'Free', status: 'Open', note: 'The public fields of a tender or funding list, with the source, licence and attribution on every row.' },
  { name: 'Atom feeds', price: 'Free', status: 'Open', note: 'What changed, the weekly digest and the regulatory tracker, for any feed reader.' },
  { name: 'Calendar feed', price: 'Free', status: 'Open', note: 'Tender and funding deadlines in your own calendar app.' },
  { name: 'Readiness check', price: 'Free', status: 'Open', note: 'Your answers stay in your browser.' },
  { name: 'Account and e-mail alerts', price: 'No price set', status: 'Not open yet', note: 'Built. Sign-in opens once a provider to send the e-mails is chosen.' },
];

export default function PricingPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Pricing', href: '/pricing' }]}
      title="Pricing"
      lead="DefenceGate is free to use. There is no paid plan and no billing, and we ask for no payment details. If a paid service is ever offered, its price and terms will be on this page before anything is charged."
    >
      <Card>
        {/* At 375 px the note goes under the name and the table fits without scrolling sideways (QA m-7) */}
        <DataTable label="What is offered and what it costs" minWidth={280}>
          <thead>
            <tr><th scope="col">What</th><th scope="col">Price</th><th scope="col">Status</th><th scope="col" className="hidden sm:table-cell">Note</th></tr>
          </thead>
          <tbody>
            {OFFER.map((p) => (
              <tr key={p.name}>
                <th scope="row" className="!align-top sm:whitespace-nowrap">
                  {p.name}
                  <span className="mt-1 block font-normal text-ink-muted sm:hidden">{p.note}</span>
                </th>
                <td className="font-mono sm:whitespace-nowrap">{p.price}</td>
                <td className="font-bold sm:whitespace-nowrap">{p.status}</td>
                <td className="hidden text-ink-muted sm:table-cell">{p.note}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </Card>
    </ContentPage>
  );
}
