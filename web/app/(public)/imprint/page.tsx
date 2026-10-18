import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { ContentPage, ContentSection, Placeholder } from '@/components/dg/content-page';
import { Fact } from '@/components/dg/facts-grid';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Imprint',
  description: 'Provider details for DefenceGate. Draft: the details are not provided yet.',
  path: '/imprint',
  noindex: true,
});

/** Every fact here comes from the owner. None is invented. */
const FIELDS = ['Provider', 'Legal form', 'Address', 'Registration number', 'VAT number', 'Represented by', 'Contact'];

export default function ImprintPage() {
  return (
    <ContentPage
      draft
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Imprint', href: '/imprint' }]}
      title="Imprint"
      lead="The provider details are not filled in yet."
    >
      <ContentSection title="Provider">
        {/* Seven rows in two columns, the last across both: every value is still the owner's to fill. */}
        <dl className="m-0 grid gap-x-8 border-b border-line sm:grid-cols-2">
          {FIELDS.map((f, i) => (
            <Fact key={f} label={f} wide={i === FIELDS.length - 1}><Placeholder>to be provided</Placeholder></Fact>
          ))}
        </dl>
      </ContentSection>
    </ContentPage>
  );
}
