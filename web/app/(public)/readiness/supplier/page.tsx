import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { Callout } from '@/components/dg/blocks';
import { ContentPage, PageSection } from '@/components/dg/content-page';
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
      <PageSection title="Who this is for">
        <div className="flex max-w-prose flex-col gap-3 text-body" data-supplier-audience>
          <p className="m-0">
            Manufacturers in Spain that make civilian products today, such as automotive components, castings, machined parts or electronics, and
            want to supply defence buyers: the Ministry of Defence, the NATO Support and Procurement Agency (NSPA), and the prime contractors that
            build for them.
          </p>
          <p className="m-0">
            The check reads your answers against the rules of the Spanish Ministry of Defence supplier route, NATO supply and the EU defence
            programmes, each with its source. It lists what you already hold, what you need now, and what usually comes with a first contract,
            such as the PECAL quality certificate. Once you save, your results link to a report you can print or save as a PDF.
          </p>
          <p className="m-0">
            It does not find contracts and does not say that you will win one: each buyer sets its conditions in the tender documents. Where an
            answer needs a classification or a legal reading (export control, US-origin components, a foreign investor, a security clearance), it
            says so and gives no answer of its own. A company established elsewhere can use it too; the Spanish rules then do not apply.
          </p>
        </div>
      </PageSection>
      <Callout title="Your answers stay in this browser">
        <p className="m-0">They are saved in this browser, on this device, together with the answers of the readiness check. There is no account and no copy on our server.</p>
        <p className="m-0">The only thing that leaves your browser is the request that computes the verdict, with the answers the rules read. The server does not store or log them.</p>
      </Callout>
      <SupplierForm />
    </ContentPage>
  );
}
