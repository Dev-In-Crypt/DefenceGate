import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { ContentPage, ContentSection, Placeholder } from '@/components/dg/content-page';

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
        <dl className="m-0 flex flex-col">
          {FIELDS.map((f, i) => (
            <div key={f} className={`grid gap-1 py-3 sm:grid-cols-[200px_1fr] sm:gap-4${i < FIELDS.length - 1 ? ' border-b border-line' : ''}`}>
              <dt className="text-body font-semibold">{f}</dt>
              <dd className="m-0 text-body"><Placeholder>to be provided</Placeholder></dd>
            </div>
          ))}
        </dl>
      </ContentSection>
    </ContentPage>
  );
}
