import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { WHAT_IS_SENT } from '@/lib/sent-copy';
import { Callout } from '@/components/dg/blocks';
import { AboutData } from '@/components/dg/about-data';
import { ContentPage } from '@/components/dg/content-page';
import { SupplierForm } from '@/components/readiness/supplier';

export const metadata: Metadata = buildMetadata({
  title: 'Supplier profile: who to approach in defence',
  // WP-130: under 160 characters, so the search snippet is the whole sentence (the trim kept only the 48 before the colon)
  description: 'Say what you make (CPV codes) and what you hold: see who wins defence contracts for it in five countries, who buys it and which rules apply to you.',
  path: '/readiness/supplier',
});

type Props = { searchParams: Promise<{ offer?: string | string[] }> };

export default async function SupplierPage({ searchParams }: Props) {
  const asked = (await searchParams).offer;
  const offer = asked === 'services' || asked === 'products' ? asked : null;
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Check my company', href: '/check' }, { label: 'Supplier profile', href: '/readiness/supplier' }]}
      title="Supplier profile"
      lead="Say what you make and what you hold: the results show who wins defence contracts for it, who buys it, and what their rules ask of you."
    >
      {/* WP-88: who it is for and what it gives, collapsed; the form follows one sentence. */}
      <AboutData summary="Who this is for and what you get">
        <div className="flex max-w-prose flex-col gap-3" data-supplier-audience>
          <p className="m-0">
            For a company that makes parts or materials, or provides services such as logistics, transport, fuel, facility services, catering, maintenance or training, and wants defence work. Manufacturers in Spain that make civilian products today, such as automotive components, castings, machined parts or electronics, and
            want to supply defence buyers: the Ministry of Defence, the NATO Support and Procurement Agency (NSPA), and the prime contractors that
            build for them.
          </p>
          <p className="m-0">
            From your CPV codes it lists first who to approach: the companies that won defence-scope contracts for them in Spain, Germany, France,
            Poland and the Netherlands over the last three years, with prime contractors and large defence groups marked, since automotive suppliers
            usually enter defence as their subcontractors. Then who buys those codes.
          </p>
          <p className="m-0">
            Then the rules: your answers against the Spanish Ministry of Defence supplier route, NATO supply and the EU defence programmes, each with
            its source, and what you already hold, what you need now, and what usually comes with a first contract, such as the PECAL quality
            certificate, each step with the free guide and the regional grants that have paid for it. Once you save, your results link to a report
            you can print or save as a PDF.
          </p>
          <p className="m-0">
            It does not find contracts and does not say that you will win one: each buyer sets its conditions in the tender documents. Where an
            answer needs a classification or a legal reading (export control, US-origin components, a foreign investor, a security clearance), it
            says so and gives no answer of its own. A company established elsewhere can use it too; the Spanish rules then do not apply.
          </p>
        </div>
      </AboutData>
      <Callout title="Your answers are not stored on our server">
        <AboutData summary="What is kept and what is sent">
        <p className="m-0">They are saved in this browser, on this device, together with the answers of the readiness check. There is no account and no copy on our server.</p>
        <p className="m-0" data-what-is-sent>{WHAT_IS_SENT}</p>
        </AboutData>
      </Callout>
      <SupplierForm offer={offer} />
    </ContentPage>
  );
}
