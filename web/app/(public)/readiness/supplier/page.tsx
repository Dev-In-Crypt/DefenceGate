import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { Callout } from '@/components/dg/blocks';
import { ContentPage } from '@/components/dg/content-page';
import { SupplierForm } from '@/components/readiness/supplier';

export const metadata: Metadata = buildMetadata({
  title: 'Supplier profile: what a parts or materials maker needs to supply defence buyers',
  description: 'Say what you make (CPV codes), the processes you run, the certificates and registrations you hold, and see which rules of the Spanish Ministry of Defence route, NATO supply and the EU programmes apply to you. Every rule shows its source.',
  path: '/readiness/supplier',
});

export default function SupplierPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Readiness check', href: '/readiness' }, { label: 'Supplier profile', href: '/readiness/supplier' }]}
      title="Supplier profile"
      lead="For a company that makes parts or materials and wants to supply defence buyers. Say what you make and what you hold; the results show, rule by rule, what the buyers' routes ask of you."
    >
      <Callout title="Your answers stay in this browser">
        <p className="m-0">They are saved in this browser, on this device, together with the answers of the readiness check. There is no account and no copy on our server.</p>
        <p className="m-0">The only thing that leaves your browser is the request that computes the verdict, with the answers the rules read. The server does not store or log them.</p>
      </Callout>
      <SupplierForm />
    </ContentPage>
  );
}
